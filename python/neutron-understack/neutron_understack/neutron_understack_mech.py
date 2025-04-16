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
from oslo_config import cfg

from neutron_understack import config
from neutron_understack import utils
from neutron_understack import vlan_group_name_convention
from neutron_understack.nautobot import Nautobot
from neutron_understack.nautobot import VlanPayload
from neutron_understack.trunk import UnderStackTrunkDriver
from neutron_understack.undersync import Undersync

LOG = logging.getLogger(__name__)

config.register_ml2_type_understack_opts(cfg.CONF)
config.register_ml2_understack_opts(cfg.CONF)


class UnderstackDriver(MechanismDriver):
    # See MechanismDriver docs for resource_provider_uuid5_namespace
    resource_provider_uuid5_namespace = UUID("6eae3046-4072-11ef-9bcf-d6be6370a162")

    @property
    def connectivity(self):  # type: ignore
        return portbindings.CONNECTIVITY_L2

    def initialize(self):
        conf = cfg.CONF.ml2_understack
        self.nb = Nautobot(conf.nb_url, conf.nb_token)
        self.undersync = Undersync(conf.undersync_token, conf.undersync_url)
        self.trunk_driver = UnderStackTrunkDriver.create(self)
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

    def create_network_precommit(self, context):
        pass

    def create_network_postcommit(self, context):
        network = context.current
        network_id = network["id"]
        network_name = network["name"]
        project_id = network["project_id"]
        external = network["router:external"]
        provider_type = network.get("provider:network_type")
        physnet = network.get("provider:physical_network")
        segmentation_id = network.get("provider:segmentation_id")
        conf = cfg.CONF.ml2_understack

        if provider_type not in [p_const.TYPE_VLAN, p_const.TYPE_VXLAN]:
            return

        ucvni_group = conf.ucvni_group
        ucvni_response = self.nb.ucvni_create(
            network_id=network_id,
            project_id=project_id,
            ucvni_group=ucvni_group,
            network_name=network_name,
            segmentation_id=segmentation_id,
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

        if provider_type != p_const.TYPE_VXLAN:
            return

        self.nb.ucvni_delete(network_id)

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
                network_uuid=network_uuid,
                subnet_uuid=subnet_uuid,
            )
            self.nb.set_svi_role_on_network(
                role="svi_vxlan_anycast_gateway",
                network_uuid=network_uuid,
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

    def _fetch_subports_network_ids(self, trunk_details: dict | None) -> list:
        if trunk_details is None:
            return []

        network_uuids = [
            utils.fetch_subport_network_id(subport.get("port_id"))
            for subport in trunk_details.get("sub_ports", [])
        ]
        return network_uuids

    def update_port_postcommit(self, context):
        """Tenant network port cleanup in the UnderCloud infrastructure.

        This is triggered in the update_port_postcommit call as in the
        delete_port_postcommit call there is no binding profile information
        anymore, hence there is no way for us to identify which baremetal port
        needs cleanup.

        Only in the update_port_postcommit do we have access to the original
        context, from which we can access the binding information.

        # TODO: garbage collection of unused VLAN-type network segments.  We
        # create these dynamic segments on the fly so they might get left behind
        # as the ports disappear.   If a VLAN is left in a cabinet with nobody
        # using it, it can be deleted.
        """
        vlan_group_name = self._vlan_group_name(context)

        baremetal_vnic = context.current["binding:vnic_type"] == "baremetal"
        current_vif_unbound = context.vif_type == portbindings.VIF_TYPE_UNBOUND
        original_vif_other = context.original_vif_type == portbindings.VIF_TYPE_OTHER
        current_vif_other = context.vif_type == portbindings.VIF_TYPE_OTHER

        if baremetal_vnic and current_vif_unbound and original_vif_other:
            self._tenant_network_port_cleanup(context)
            if vlan_group_name:
                self.invoke_undersync(vlan_group_name)
        elif current_vif_other and vlan_group_name:
            self.invoke_undersync(vlan_group_name)

    def _tenant_network_port_cleanup(self, context: PortContext):
        trunk_details = context.current.get("trunk_details", {})
        segment_id = context.original_top_bound_segment["id"]
        original_binding = context.original["binding:profile"]
        connected_interface_uuid = utils.fetch_connected_interface_uuid(
            original_binding, self.nb
        )

        if not utils.ports_bound_to_segment(segment_id):
            context.release_dynamic_segment(segment_id)
            self.nb.delete_vlan(segment_id)

        networks_to_remove = {segment_id}

        LOG.debug(
            "update_port_postcommit removing vlans %s from interface %s ",
            networks_to_remove,
            connected_interface_uuid,
        )

        self.nb.remove_port_network_associations(
            connected_interface_uuid, networks_to_remove
        )

        if trunk_details:
            self.trunk_driver.clean_trunk(
                trunk_details=trunk_details,
                binding_profile=original_binding,
                host=context.original_host,
            )

    def delete_port_precommit(self, context):
        pass

    def delete_port_postcommit(self, context):
        # Only clean up provisioning ports.  Everything else is left to get
        # cleaned up upon the next change in that cabinet.
        vlan_group_name = self._vlan_group_name(context)
        if vlan_group_name and is_provisioning_network(context.current["network_id"]):
            # Signals end of the provisioning / cleaning cycle, so we
            # put the port back to its normal tenant mode:
            self._set_nautobot_port_status(context, "Active")
            self.invoke_undersync(vlan_group_name)

    def bind_port(self, context: PortContext) -> None:
        """Bind the VXLAN network segment and allocate dynamic VLAN segments.

        Our "context" knows a Port, a Network and a list of Segments.

        We find the first (hopefully only) segment of type vxlan.  This is the
        one we bind.  There may be other segments, but we only bind the vxlan
        one.

        We obtain the dynamic segment for this (network, vlan_group) pair.

        If there are no VXLAN segments, then bind a VLAN segment instead (this
        is required for VLAN-type networks like the provisioning network).

        We configure the nautobot switch interface with the new VLAN(s).

        Then make the required call in to the black box: context.set_binding
        which tells the framework that we have dealt with this port and they
        don't need to retry or handle this some other way.

        We expect to receive a call to update_port_postcommit soon after this,
        which means that changes made here will get pushed to the switch at that
        time.
        """
        if is_provisioning_network(context.current["network_id"]):
            self._set_nautobot_port_status(context, "Provisioning-Interface")

        for segment in context.network.network_segments:
            if segment[api.NETWORK_TYPE] == p_const.TYPE_VXLAN:
                self._bind_port_segment(context, segment)
                return

    def _bind_port_segment(self, context: PortContext, segment):
        network_id = context.current["network_id"]
        connected_interface_uuid = utils.fetch_connected_interface_uuid(
            context.current["binding:profile"], self.nb
        )
        vlan_group_name = self._vlan_group_name(context)
        if vlan_group_name is None:
            raise Exception("bind_port_segment: no switch info in local_link_info")

        LOG.debug(
            "bind_port_segment: interface %s network %s vlan group %s",
            connected_interface_uuid,
            network_id,
            vlan_group_name,
        )

        dynamic_segment = context.allocate_dynamic_segment(
            segment={
                "network_type": p_const.TYPE_VLAN,
                "physical_network": vlan_group_name,
            },
        )

        LOG.debug("bind_port_segment: Native VLAN segment %s", dynamic_segment)
        dynamic_segment_vlan_id = dynamic_segment["segmentation_id"]

        self.nb.set_port_vlan_associations(
            interface_uuid=connected_interface_uuid,
            native_vlan_id=dynamic_segment_vlan_id,
            allowed_vlans_ids={dynamic_segment_vlan_id},
            vlan_group_name=vlan_group_name,
        )

        trunk_details = context.current.get("trunk_details") or {}
        port_id = context.current["id"]
        if trunk_details:
            self.trunk_driver.configure_trunk(trunk_details, port_id)

        LOG.debug("set_binding for segment: %s", segment)
        context.set_binding(
            segment_id=dynamic_segment[api.ID],
            vif_type=portbindings.VIF_TYPE_OTHER,
            vif_details={},
            status=p_const.PORT_STATUS_ACTIVE,
        )

    def invoke_undersync(self, vlan_group_name: str):
        self.undersync.sync_devices(
            vlan_group=vlan_group_name,
            dry_run=cfg.CONF.ml2_understack.undersync_dry_run,
        )

    def _vlan_group_name(self, context: PortContext) -> str | None:
        binding_profile = context.current.get("binding:profile", {})
        local_link_info = binding_profile.get("local_link_information", [])
        switch_names = [
            link["switch_info"] for link in local_link_info if "switch_info" in link
        ]
        if switch_names:
            return vlan_group_name_convention.for_switch(switch_names[0])

    def check_vlan_transparency(self, context):
        pass

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

    def _set_nautobot_port_status(self, context: PortContext, status: str):
        profile = context.current["binding:profile"]
        interface_uuid = utils.fetch_connected_interface_uuid(profile, self.nb)
        LOG.debug("Set interface %s to %s status", interface_uuid, status)
        self.nb.configure_port_status(interface_uuid, status=status)


def is_provisioning_network(network_id: str) -> bool:
    provisioning_network = (
        cfg.CONF.ml2_understack.provisioning_network
        or cfg.CONF.ml2_type_understack.provisioning_network
    )
    return network_id == provisioning_network
