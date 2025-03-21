import logging
from uuid import UUID

import neutron_lib.api.definitions.portbindings as portbindings
from neutron.plugins.ml2.driver_context import PortContext
from neutron_lib import constants as p_const
from neutron_lib.api.definitions import segment as segment_def
from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.plugins.ml2 import api
from neutron_lib.plugins.ml2.api import MechanismDriver
from neutron_lib.plugins.ml2.api import NetworkContext
from oslo_config import cfg

from neutron_understack import config
from neutron_understack import utils
from neutron_understack.nautobot import Nautobot
from neutron_understack.nautobot import VlanPayload
from neutron_understack.trunk import UnderStackTrunkDriver
from neutron_understack.undersync import Undersync
from neutron_understack.vlan_manager import VlanManager

LOG = logging.getLogger(__name__)

config.register_ml2_type_understack_opts(cfg.CONF)
config.register_ml2_understack_opts(cfg.CONF)


class UnderstackDriver(MechanismDriver):
    # See MechanismDriver docs for resource_provider_uuid5_namespace
    resource_provider_uuid5_namespace = UUID("6eae3046-4072-11ef-9bcf-d6be6370a162")

    @property
    def connectivity(self):
        return portbindings.CONNECTIVITY_L2

    def initialize(self):
        conf = cfg.CONF.ml2_understack
        self.nb = Nautobot(conf.nb_url, conf.nb_token)
        self.undersync = Undersync(conf.undersync_token, conf.undersync_url)
        self.trunk_driver = UnderStackTrunkDriver.create(self)
        self.vlan_manager = VlanManager(self.nb, conf)
        self.subscribe()

    def subscribe(self):
        registry.subscribe(
            self._create_segment,
            resources.SEGMENT,
            events.PRECOMMIT_CREATE,
            cancellable=True,
        )
        registry.subscribe(
            self._delete_segment,
            resources.SEGMENT,
            events.BEFORE_DELETE,
            cancellable=True,
        )

    def create_network_precommit(self, context: NetworkContext):
        if cfg.CONF.ml2_understack.enforce_unique_vlans_in_fabric:
            self.vlan_manager.create_vlan_for_network(context)

    def create_network_postcommit(self, context):
        network = context.current
        network_id = network["id"]
        network_name = network["name"]
        project_id = network["project_id"]
        external = network["router:external"]
        provider_type = network.get("provider:network_type")
        segmentation_id = network.get("provider:segmentation_id")
        physnet = network.get("provider:physical_network")
        conf = cfg.CONF.ml2_understack

        if provider_type not in [p_const.TYPE_VLAN, p_const.TYPE_VXLAN]:
            return
        ucvni_group = conf.ucvni_group
        ucvni_response = self.nb.ucvni_create(
            network_id=network_id,
            project_id=project_id,
            ucvni_group=ucvni_group,
            network_name=network_name,
        )
        LOG.info(
            "network %(net_id)s has been added on ucvni_group %(ucvni_group)s, "
            "physnet %(physnet)s",
            {
                "net_id": network_id,
                "nautobot_ucvni_uuid": ucvni_response.get("id"),
                "nautobot_tenant_id": ucvni_response.get("tenant", {}).get("id"),
                "ucvni_group": ucvni_group,
                "physnet": physnet,
            },
        )
        self._create_nautobot_namespace(network_id, external)

        if provider_type != p_const.TYPE_VLAN:
            return

        vlan_group_id_and_vlan_tag = self.nb.prep_switch_interface(
            connected_interface_id=conf.network_node_switchport_uuid,
            ucvni_uuid=network_id,
            modify_native_vlan=False,
            vlan_tag=int(segmentation_id),
        )
        self.undersync.sync_devices(
            vlan_group_uuids=str(vlan_group_id_and_vlan_tag["vlan_group_id"]),
            dry_run=cfg.CONF.ml2_understack.undersync_dry_run,
        )

    def update_network_precommit(self, context):
        pass

    def update_network_postcommit(self, context):
        pass

    def delete_network_precommit(self, context):
        pass

    def delete_network_postcommit(self, context):
        network = context.current
        network_id = network["id"]
        external = network["router:external"]
        provider_type = network.get("provider:network_type")
        physnet = network.get("provider:physical_network")

        conf = cfg.CONF.ml2_understack
        ucvni_group = conf.ucvni_group

        if provider_type == p_const.TYPE_VLAN:
            vlan_group_id = self.nb.detach_port(
                connected_interface_id=conf.network_node_switchport_uuid,
                ucvni_uuid=network_id,
            )
            self.nb.ucvni_delete(network_id)
            self.undersync.sync_devices(
                vlan_group_uuids=str(vlan_group_id),
                dry_run=cfg.CONF.ml2_understack.undersync_dry_run,
            )
        elif provider_type == p_const.TYPE_VXLAN:
            network_segments = utils.valid_network_segments(context.network_segments)
            vlans_to_delete = [segment.get("id") for segment in network_segments]
            self.nb.delete_vlans(
                vlan_ids=vlans_to_delete,
            )
            self.nb.ucvni_delete(network_id)
        else:
            return

        LOG.info(
            "network %(net_id)s has been deleted from ucvni_group %(ucvni_group)s, "
            "physnet %(physnet)s",
            {"net_id": network_id, "ucvni_group": ucvni_group, "physnet": physnet},
        )
        if not external:
            self._fetch_and_delete_nautobot_namespace(network_id)

    def create_subnet_precommit(self, context):
        pass

    def create_subnet_postcommit(self, context):
        """Create Prefix in Nautobot to represent this Subnet.

        We divide the world into two kinds of Subnet:

        1) external subnets

           Have a public IP address, hence they all go into a single shared
           namespace.

           Will have an SVI configured on the leaf switch, which is achieved by
           associating them with a VNI in nautobot.

        2) non-external subnets

           Have arbitrary IP space, so each Network has its own namespace which
           means that two networks can both use the same IP block.

           Don't have an SVI, which means we don't associate them with a VNI in
           nautobot.

        The openstack tenant_id is a hex string without dashes.  We convert this
        to a normal UUID format for compatibility with Nautobot.
        """
        subnet_uuid = context.current["id"]
        network_uuid = context.current["network_id"]
        prefix = context.current["cidr"]
        external = context.current["router:external"]
        tenant_uuid = context.current["tenant_id"]

        if tenant_uuid:
            tenant_uuid = str(UUID(tenant_uuid))

        if external:
            namespace = cfg.CONF.ml2_understack.shared_nautobot_namespace_name
        else:
            namespace = network_uuid

        self.nb.subnet_create(
            subnet_uuid=subnet_uuid,
            prefix=prefix,
            namespace_name=namespace,
            tenant_uuid=tenant_uuid,
        )

        if external:
            self.nb.associate_subnet_with_network(
                role="svi_vxlan_anycast_gateway",
                network_uuid=network_uuid,
                subnet_uuid=subnet_uuid,
            )

        LOG.info(
            "subnet with ID: %s and prefix %s has been "
            "created in Nautobot namespace %s",
            subnet_uuid,
            prefix,
            namespace,
        )

    def update_subnet_precommit(self, context):
        pass

    def update_subnet_postcommit(self, context):
        pass

    def delete_subnet_precommit(self, context):
        pass

    def delete_subnet_postcommit(self, context):
        pass

        subnet = context.current
        subnet_uuid = subnet["id"]
        prefix = subnet["cidr"]

        self.nb.subnet_delete(subnet_uuid)
        LOG.info(
            "subnet with ID: %(uuid)s and prefix %(prefix)s has been "
            "deleted in Nautobot",
            {"prefix": prefix, "uuid": subnet_uuid},
        )

    def create_port_precommit(self, context):
        pass

    def create_port_postcommit(self, context):
        pass

    def update_port_precommit(self, context):
        pass

    def _fetch_subports_network_ids(self, trunk_details: dict) -> list:
        network_uuids = [
            utils.fetch_subport_network_id(subport.get("port_id"))
            for subport in trunk_details.get("sub_ports", [])
        ]
        return network_uuids

    def _configure_trunk(
        self, trunk_details: dict, connected_interface_uuid: str
    ) -> None:
        network_uuids = self._fetch_subports_network_ids(trunk_details)
        for network_uuid in network_uuids:
            self.nb.prep_switch_interface(
                connected_interface_id=connected_interface_uuid,
                ucvni_uuid=network_uuid,
                modify_native_vlan=False,
                vlan_tag=None,
            )

    def update_port_postcommit(self, context):
        self._delete_tenant_port_on_unbound(context)

    def delete_port_precommit(self, context):
        pass

    def delete_port_postcommit(self, context):
        provisioning_network = (
            cfg.CONF.ml2_understack.provisioning_network
            or cfg.CONF.ml2_type_understack.provisioning_network
        )

        network_id = context.current["network_id"]
        if network_id == provisioning_network:
            connected_interface_uuid = utils.fetch_connected_interface_uuid(
                context.current["binding:profile"], LOG
            )
            port_status = "Active"
            configure_port_status_data = self.nb.configure_port_status(
                connected_interface_uuid, port_status
            )
            switch_uuid = configure_port_status_data.get("device", {}).get("id")
            nb_vlan_group_id = UUID(self.nb.fetch_vlan_group_uuid(switch_uuid))
            self.undersync.sync_devices(
                vlan_group_uuids=str(nb_vlan_group_id),
                dry_run=cfg.CONF.ml2_understack.undersync_dry_run,
            )

    def _configure_switchport_on_bind(self, context: PortContext) -> None:
        trunk_details = context.current.get("trunk_details", {})
        network_id = context.current["network_id"]
        network_type = context.network.current.get("provider:network_type")
        connected_interface_uuid = utils.fetch_connected_interface_uuid(
            context.current["binding:profile"], LOG
        )

        if trunk_details:
            self._configure_trunk(trunk_details, connected_interface_uuid)
        if network_type == p_const.TYPE_VLAN:
            vlan_tag = int(context.network.current.get("provider:segmentation_id"))
        else:
            vlan_tag = None
        nb_vlan_group_id = self.update_nautobot(
            network_id, connected_interface_uuid, vlan_tag
        )

        self.undersync.sync_devices(
            vlan_group_uuids=str(nb_vlan_group_id),
            dry_run=cfg.CONF.ml2_understack.undersync_dry_run,
        )

    def bind_port(self, context: PortContext) -> None:
        for segment in context.network.network_segments:
            if self.check_segment(segment):
                context.set_binding(
                    segment[api.ID],
                    portbindings.VIF_TYPE_OTHER,
                    {},
                    status=p_const.PORT_STATUS_ACTIVE,
                )
                LOG.debug("Bound segment: %s", segment)
                self._configure_switchport_on_bind(context)
                return
            else:
                LOG.debug(
                    "Refusing to bind port for segment ID %(id)s, "
                    "segment %(seg)s, phys net %(physnet)s, and "
                    "network type %(nettype)s",
                    {
                        "id": segment[api.ID],
                        "seg": segment[api.SEGMENTATION_ID],
                        "physnet": segment[api.PHYSICAL_NETWORK],
                        "nettype": segment[api.NETWORK_TYPE],
                    },
                )

    def check_segment(self, segment):
        """Verify a segment is valid for the Understack MechanismDriver.

        Verify the requested segment is supported by Understack and return True or
        False to indicate this to callers.
        """
        network_type = segment[api.NETWORK_TYPE]
        return network_type in [
            p_const.TYPE_VXLAN,
            p_const.TYPE_VLAN,
        ]

    def check_vlan_transparency(self, context):
        pass

    def update_nautobot(
        self,
        network_id: str,
        connected_interface_uuid: str,
        vlan_tag: int | None,
    ) -> UUID:
        """Updates Nautobot with the new network ID and connected interface UUID.

        If the network ID is a provisioning network, sets the interface status to
        "Provisioning-Interface" and configures Nautobot for provisioning mode.
        If the network ID is a tenant network, sets the interface status to a tenant
        status and triggers a Nautobot Job to update the switch interface for tenant
        mode. In either case, retrieves and returns the VLAN Group UUID for the
        specified network and interface.
        :param network_id: The ID of the network.
        :param connected_interface_uuid: The UUID of the connected interface.
        :return: The VLAN group UUID.
        """
        provisioning_network = (
            cfg.CONF.ml2_understack.provisioning_network
            or cfg.CONF.ml2_type_understack.provisioning_network
        )

        if network_id == provisioning_network:
            port_status = "Provisioning-Interface"
            configure_port_status_data = self.nb.configure_port_status(
                connected_interface_uuid, port_status
            )
            switch_uuid = configure_port_status_data.get("device", {}).get("id")
            return UUID(self.nb.fetch_vlan_group_uuid(switch_uuid))
        else:
            vlan_group_id = self.nb.prep_switch_interface(
                connected_interface_id=connected_interface_uuid,
                ucvni_uuid=network_id,
                vlan_tag=vlan_tag,
            )["vlan_group_id"]
            return UUID(vlan_group_id)

    def _clean_trunks(self, trunk_details: dict, connected_interface_uuid: str) -> None:
        network_uuids = self._fetch_subports_network_ids(trunk_details)
        for network_uuid in network_uuids:
            self.nb.detach_port(connected_interface_uuid, network_uuid)

    def _delete_tenant_port_on_unbound(self, context):
        """Tenant network port cleanup in the UnderCloud infrastructure.

        This is triggered in the update_port_postcommit call as in the
        delete_port_postcommit call there is no binding profile information
        anymore, hence there is no way for us to identify which baremetal port
        needs cleanup.

        Only in the update_port_postcommit we have access to the original context,
        from which we can access the binding information.
        """
        if (
            context.current["binding:vnic_type"] == "baremetal"
            and context.vif_type == portbindings.VIF_TYPE_UNBOUND
            and context.original_vif_type == portbindings.VIF_TYPE_OTHER
        ):
            connected_interface_uuid = utils.fetch_connected_interface_uuid(
                context.original["binding:profile"], LOG
            )
            trunk_details = context.current.get("trunk_details", {})
            if trunk_details:
                self._clean_trunks(trunk_details, connected_interface_uuid)

            network_id = context.current["network_id"]
            nb_vlan_group_id = UUID(
                self.nb.detach_port(connected_interface_uuid, network_id)
            )
            self.undersync.sync_devices(
                vlan_group_uuids=str(nb_vlan_group_id),
                dry_run=cfg.CONF.ml2_understack.undersync_dry_run,
            )

    def _fetch_and_delete_nautobot_namespace(self, name: str) -> None:
        namespace_uuid = self.nb.fetch_namespace_by_name(name)
        LOG.info(
            "namespace %(name)s nautobot uuid: %(ns_uuid)s",
            {"name": name, "ns_uuid": namespace_uuid},
        )
        self.nb.namespace_delete(namespace_uuid)
        LOG.info(
            "namespace with name: %(name)s and uuid: %(ns_uuid)s has been deleted "
            "from nautobot",
            {"name": name, "ns_uuid": namespace_uuid},
        )

    def _create_nautobot_namespace(
        self, network_id: str, network_is_external: bool
    ) -> None:
        if not network_is_external:
            self.nb.namespace_create(name=network_id)
            LOG.info(
                "namespace with name %(network_id)s has been created in Nautobot",
                {"network_id": network_id},
            )
        else:
            shared_namespace = cfg.CONF.ml2_understack.shared_nautobot_namespace_name
            LOG.info(
                "Network %(network_id)s is external, nautobot namespace "
                "%(shared_nautobot_namespace)s will be used to house all "
                "prefixes in this network",
                {
                    "network_id": network_id,
                    "shared_nautobot_namespace": shared_namespace,
                },
            )

    def _create_segment(self, resource, event, trigger, payload):
        self._create_vlan(payload.latest_state)

    def _delete_segment(self, resource, event, trigger, payload):
        self._delete_vlan(payload.latest_state)

    def _create_vlan(self, segment):
        if not utils.is_valid_vlan_network_segment(segment):
            return

        vlan_payload = VlanPayload(
            id=segment.get("id"),
            vid=segment.get(segment_def.SEGMENTATION_ID),
            vlan_group_name=segment.get(segment_def.PHYSICAL_NETWORK),
            network_id=segment.get("network_id"),
        )

        LOG.info(
            "creating vlan in nautobot for segment %(segment)s",
            {"segment": segment},
        )
        self.nb.create_vlan_and_associate_vlan_to_ucvni(vlan_payload)

    def _delete_vlan(self, segment):
        if not utils.is_valid_vlan_network_segment(segment):
            return
        LOG.info(
            "deleting vlan in nautobot for segment %(segment)s",
            {"segment": segment},
        )
        self.nb.delete_vlan(
            vlan_id=segment.get("id"),
        )
