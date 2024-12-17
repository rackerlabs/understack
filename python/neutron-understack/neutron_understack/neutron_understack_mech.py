import json
import logging
from pprint import pprint
from uuid import UUID

import neutron_lib.api.definitions.portbindings as portbindings
from neutron_lib import constants as p_const
from neutron_lib.plugins.ml2 import api
from neutron_lib.plugins.ml2.api import (
    MechanismDriver,
    NetworkContext,
    PortContext,
    SubnetContext,
)
from oslo_config import cfg

from neutron_understack import config
from neutron_understack.nautobot import Nautobot
from neutron_understack.undersync import Undersync

LOG = logging.getLogger(__name__)


config.register_ml2_type_understack_opts(cfg.CONF)
config.register_ml2_understack_opts(cfg.CONF)


def dump_context(
    context: NetworkContext | SubnetContext | PortContext,
) -> dict:
    # RESOURCE_ATTRIBUTE_MAP
    # from neutron_lib.api.definitions import network, subnet, port, portbindings
    # The properties of a NetworkContext.current are defined in
    #   network.RESOURCE_ATTRIBUTE_MAP
    # The properties of a SubnetContext.current are defined in
    #   subnet.RESOURCE_ATTRIBUTE_MAP
    # The properties of a PortContext.current are defined in
    #   port.RESOURCE_ATTRIBUTE_MAP
    attr_map = {
        NetworkContext: ("current", "original", "network_segments"),
        SubnetContext: ("current", "original"),
        PortContext: (
            "current",
            "original",
            "status",
            "original_status",
            "network",
            "binding_levels",
            "original_binding_levels",
            "top_bound_segment",
            "original_top_bound_segment",
            "bottom_bound_segment",
            "original_bottom_bound_segment",
            "host",
            "original_host",
            "vif_type",
            "original_vif_type",
            "vif_details",
            "original_vif_details",
            "segments_to_bind",
        ),
    }
    retval = {"errors": [], "other_attrs": []}
    if isinstance(context, NetworkContext):
        attrs_to_dump = attr_map[NetworkContext]
    elif isinstance(context, SubnetContext):
        attrs_to_dump = attr_map[SubnetContext]
    elif isinstance(context, PortContext):
        attrs_to_dump = attr_map[PortContext]
    else:
        retval["errors"].append(f"Error: unknown object type {type(context)}")
        return retval

    attrs = vars(context)
    for attr in attrs:
        if attr in attrs_to_dump:
            try:
                val = getattr(context, attr)
                retval.update({attr: val})
            except Exception as e:
                retval["errors"].append(f"Error dumping {attr}: {str(e)}")
        else:
            retval["other_attrs"].append(attr)
    return retval


def log_call(
    method: str, context: NetworkContext | SubnetContext | PortContext
) -> None:
    data = dump_context(context)
    data.update({"method": method})
    try:
        jsondata = json.dumps(data)
    except Exception as e:
        LOG.error(
            "failed to dump %s object to JSON on %s call: %s",
            str(context),
            method,
            str(e),
        )
        return
    LOG.info("%s method called with data: %s", method, jsondata)
    LOG.debug("%s method executed with context:", method)
    pprint(context.current)


class UnderstackDriver(MechanismDriver):
    # See MechanismDriver docs for resource_provider_uuid5_namespace
    resource_provider_uuid5_namespace = UUID("6eae3046-4072-11ef-9bcf-d6be6370a162")

    def initialize(self):
        conf = cfg.CONF.ml2_understack
        self.nb = Nautobot(conf.nb_url, conf.nb_token)
        self.undersync = Undersync(conf.undersync_token, conf.undersync_url)

    def create_network_precommit(self, context):
        log_call("create_network_precommit", context)

    def create_network_postcommit(self, context):
        log_call("create_network_postcommit", context)

        network = context.current
        network_id = network["id"]
        network_name = network["name"]
        provider_type = network.get("provider:network_type")
        segmentation_id = network.get("provider:segmentation_id")
        physnet = network.get("provider:physical_network")

        if provider_type == p_const.TYPE_VXLAN:
            conf = cfg.CONF.ml2_understack
            ucvni_group = conf.ucvni_group
            self.nb.ucvni_create(network_id, ucvni_group, network_name, segmentation_id)
            LOG.info(
                "network %(net_id)s has been added on ucvni_group %(ucvni_group)s, "
                "physnet %(physnet)s",
                {"net_id": network_id, "ucvni_group": ucvni_group, "physnet": physnet},
            )
            self.nb.namespace_create(name=network_id)
            LOG.info(
                "namespace with name %(network_id)s has been created in Nautobot",
                {"network_id": network_id},
            )

    def update_network_precommit(self, context):
        log_call("update_network_precommit", context)

    def update_network_postcommit(self, context):
        log_call("update_network_postcommit", context)

    def delete_network_precommit(self, context):
        log_call("delete_network_precommit", context)

    def delete_network_postcommit(self, context):
        log_call("delete_network_postcommit", context)

        network = context.current
        network_id = network["id"]
        provider_type = network.get("provider:network_type")
        physnet = network.get("provider:physical_network")

        if provider_type == p_const.TYPE_VXLAN:
            conf = cfg.CONF.ml2_understack
            ucvni_group = conf.ucvni_group
            self.nb.ucvni_delete(network_id)
            LOG.info(
                "network %(net_id)s has been deleted from ucvni_group %(ucvni_group)s, "
                "physnet %(physnet)s",
                {"net_id": network_id, "ucvni_group": ucvni_group, "physnet": physnet},
            )
            self._fetch_and_delete_nautobot_namespace(network_id)

    def create_subnet_precommit(self, context):
        log_call("create_subnet_precommit", context)

    def create_subnet_postcommit(self, context):
        log_call("create_subnet_postcommit", context)

        subnet = context.current
        subnet_uuid = subnet["id"]
        network_uuid = subnet["network_id"]
        prefix = subnet["cidr"]
        external = subnet["router:external"]
        shared_namespace = cfg.CONF.ml2_understack.shared_nautobot_namespace_name
        nautobot_namespace_name = network_uuid if not external else shared_namespace

        self.nb.subnet_create(subnet_uuid, prefix, nautobot_namespace_name)
        LOG.info(
            "subnet with ID: %(uuid)s and prefix %(prefix)s has been "
            "created in Nautobot",
            {"prefix": prefix, "uuid": subnet_uuid},
        )

    def update_subnet_precommit(self, context):
        log_call("update_subnet_precommit", context)

    def update_subnet_postcommit(self, context):
        log_call("update_subnet_postcommit", context)

    def delete_subnet_precommit(self, context):
        log_call("delete_subnet_precommit", context)

    def delete_subnet_postcommit(self, context):
        log_call("delete_subnet_postcommit", context)

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
        log_call("create_port_precommit", context)

    def create_port_postcommit(self, context):
        log_call("create_port_postcommit", context)

    def update_port_precommit(self, context):
        log_call("update_port_precommit", context)

    def update_port_postcommit(self, context):
        log_call("update_port_postcommit", context)

        self._delete_tenant_port_on_unbound(context)

        vif_type = context.current["binding:vif_type"]

        if vif_type != portbindings.VIF_TYPE_OTHER:
            return

        network_id = context.current["network_id"]
        connected_interface_uuid = self.fetch_connected_interface_uuid(context.current)
        nb_vlan_group_id = self.update_nautobot(network_id, connected_interface_uuid)

        self.undersync.sync_devices(
            vlan_group_uuids=str(nb_vlan_group_id),
            dry_run=cfg.CONF.ml2_understack.undersync_dry_run,
        )

    def delete_port_precommit(self, context):
        log_call("delete_port_precommit", context)

    def delete_port_postcommit(self, context):
        log_call("delete_port_postcommit", context)

        network_id = context.current["network_id"]

        if network_id == cfg.CONF.ml2_type_understack.provisioning_network:
            connected_interface_uuid = self.fetch_connected_interface_uuid(
                context.current
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

    def bind_port(self, context):
        log_call("bind_port", context)
        for segment in context.network.network_segments:
            if self.check_segment(segment):
                context.set_binding(
                    segment[api.ID],
                    portbindings.VIF_TYPE_OTHER,
                    {},
                    status=p_const.PORT_STATUS_ACTIVE,
                )
                LOG.debug(f"Bound segment: {segment}")
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
            p_const.TYPE_LOCAL,
            p_const.TYPE_GRE,
            p_const.TYPE_VXLAN,
            p_const.TYPE_VLAN,
            p_const.TYPE_FLAT,
        ]

    def check_vlan_transparency(self, context):
        log_call("check_vlan_transparency", context)

    def fetch_connected_interface_uuid(self, context: dict) -> str:
        """Fetches the connected interface UUID from the port context.

        :param context: The context of the port.
        :return: The connected interface UUID.
        """
        connected_interface_uuid = (
            context["binding:profile"].get("local_link_information")[0].get("port_id")
        )
        try:
            UUID(str(connected_interface_uuid))
        except ValueError:
            LOG.debug(
                "Local link information port_id is not a valid UUID type"
                " port_id: %(connected_interface_uuid)s",
                {"connected_interface_uuid": connected_interface_uuid},
            )
            raise
        return connected_interface_uuid

    def update_nautobot(self, network_id: str, connected_interface_uuid: str) -> UUID:
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
        if network_id == cfg.CONF.ml2_type_understack.provisioning_network:
            port_status = "Provisioning-Interface"
            configure_port_status_data = self.nb.configure_port_status(
                connected_interface_uuid, port_status
            )
            switch_uuid = configure_port_status_data.get("device", {}).get("id")
            return UUID(self.nb.fetch_vlan_group_uuid(switch_uuid))
        else:
            return UUID(
                self.nb.prep_switch_interface(connected_interface_uuid, network_id)
            )

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
            connected_interface_uuid = self.fetch_connected_interface_uuid(
                context.original
            )
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
