import logging
import eventlet
eventlet.monkey_patch()
from uuid import UUID

from neutron_lib import constants as p_const
from neutron_lib.api.definitions import portbindings
from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.plugins.ml2 import api
from neutron_lib.plugins.ml2.api import MechanismDriver
from oslo_config import cfg

from functools import cached_property

from neutron_understack import config
from neutron_understack import routers
from neutron_understack import utils
from neutron_understack.ironic import IronicClient
from neutron_understack.trunk import UnderStackTrunkDriver
from neutron_understack.undersync import Undersync

from .ml2_type_annotations import NetworkContext
from .ml2_type_annotations import PortContext

LOG = logging.getLogger(__name__)


SUPPORTED_VNIC_TYPES = [portbindings.VNIC_BAREMETAL, portbindings.VNIC_NORMAL]


class UnderstackDriver(MechanismDriver):
    # See MechanismDriver docs for resource_provider_uuid5_namespace
    resource_provider_uuid5_namespace = UUID("6eae3046-4072-11ef-9bcf-d6be6370a162")

    @property
    def connectivity(self):  # type: ignore
        return portbindings.CONNECTIVITY_L2

    def initialize(self):
        config.register_ml2_understack_opts(cfg.CONF)
        conf = cfg.CONF.ml2_understack
        self.undersync = Undersync(conf.undersync_token, conf.undersync_url)
        LOG.debug("Finished initializing undersync for 'understack'")
        self.trunk_driver = UnderStackTrunkDriver.create(self)
        LOG.debug("Finished initializing trunks for 'understack'")
        self.subscribe()
        LOG.debug("Finished subscribing for 'understack'")
        LOG.debug("Finished initializing 'understack'")

    @cached_property
    def ironic_client(self):
        return IronicClient()

    def subscribe(self):
        registry.subscribe(
            routers.handle_router_interface_removal,
            resources.PORT,
            events.PRECOMMIT_DELETE,
            cancellable=True,
        )

    def create_network_precommit(self, context):
        pass

    def create_network_postcommit(self, context: NetworkContext):
        pass

    def update_network_precommit(self, context: NetworkContext):
        pass

    def update_network_postcommit(self, context: NetworkContext):
        pass

    def delete_network_precommit(self, context: NetworkContext):
        pass

    def delete_network_postcommit(self, context: NetworkContext):
        pass

    def create_subnet_precommit(self, context):
        pass

    def create_subnet_postcommit(self, context):
        pass

    def update_subnet_precommit(self, context):
        pass

    def update_subnet_postcommit(self, context):
        pass

    def delete_subnet_precommit(self, context):
        pass

    def delete_subnet_postcommit(self, context):
        pass

    def create_port_precommit(self, context: PortContext):
        pass

    def create_port_postcommit(self, context: PortContext) -> None:
        # Provide network node(s) with connectivity to the networks where this
        # router port is attached to.
        #
        port = context.current
        LOG.debug(
            "Created port %(port)s on network %(net)s",
            {"port": port["id"], "net": port["network_id"]},
        )

        if utils.is_router_interface(context):
            routers.create_port_postcommit(context)

    def update_port_precommit(self, context):
        pass

    def update_port_postcommit(self, context: PortContext) -> None:
        if utils.is_baremetal_port(context):
            self._update_port_baremetal(context)

    def _update_port_baremetal(self, context: PortContext) -> None:
        current_vif_unbound = context.vif_type == portbindings.VIF_TYPE_UNBOUND
        original_vif_other = context.original_vif_type == portbindings.VIF_TYPE_OTHER
        current_vif_other = context.vif_type == portbindings.VIF_TYPE_OTHER

        if current_vif_unbound and original_vif_other:
            local_link_info = utils.local_link_from_binding_profile(
                context.original[portbindings.PROFILE]
            )
        else:
            local_link_info = utils.local_link_from_binding_profile(
                context.current[portbindings.PROFILE]
            )
        vlan_group_name = self.ironic_client.baremetal_port_physical_network(
            local_link_info
        )

        if current_vif_unbound and original_vif_other:
            self._tenant_network_port_cleanup(context)
            if vlan_group_name:
                self.invoke_undersync(vlan_group_name)
        elif current_vif_other and vlan_group_name:
            self.invoke_undersync(vlan_group_name)

    def _tenant_network_port_cleanup(self, context: PortContext):
        """Tenant network port cleanup in the UnderCloud infrastructure.

        This is triggered in the update_port_postcommit call as in the
        delete_port_postcommit call there is no binding profile information
        anymore, hence there is no way for us to identify which baremetal port
        needs cleanup.

        Only in the update_port_postcommit do we have access to the original
        context, from which we can access the binding information.
        """
        trunk_details = context.current.get("trunk_details", {})
        segment_id = context.original_top_bound_segment["id"]
        original_binding = context.original[portbindings.PROFILE]

        if not utils.ports_bound_to_segment(
            segment_id
        ) and utils.is_dynamic_network_segment(segment_id):
            context.release_dynamic_segment(segment_id)

        networks_to_remove = {segment_id}

        LOG.debug(
            "update_port_postcommit removing vlans %s from interface",
            networks_to_remove,
        )

        if trunk_details:
            self.trunk_driver.clean_trunk(
                trunk_details=trunk_details,
                binding_profile=original_binding,
                host=context.original_host,
            )

    def delete_port_precommit(self, context):
        pass

    def delete_port_postcommit(self, context: PortContext) -> None:
        if utils.is_baremetal_port(context):
            self._delete_port_baremetal(context)

    def _delete_port_baremetal(self, context: PortContext) -> None:
        # Only clean up provisioning ports. Ports with tenant networks are cleaned
        # up in _tenant_network_port_cleanup

        local_link_info = utils.local_link_from_binding_profile(
            context.current[portbindings.PROFILE]
        )
        vlan_group_name = self.ironic_client.baremetal_port_physical_network(
            local_link_info
        )

        if vlan_group_name and is_provisioning_network(context.current["network_id"]):
            # Signals end of the provisioning / cleaning cycle, so we
            # put the port back to its normal tenant mode:
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

        Then make the required call in to the black box: context.set_binding
        which tells the framework that we have dealt with this port and they
        don't need to retry or handle this some other way.

        We expect to receive a call to update_port_postcommit soon after this,
        which means that changes made here will get pushed to the switch at that
        time.
        """
        port = context.current
        LOG.debug(
            "Attempting to bind port %(port)s on network %(net)s",
            {"port": port["id"], "net": port["network_id"]},
        )

        vnic_type = port.get(portbindings.VNIC_TYPE, portbindings.VNIC_NORMAL)
        if vnic_type not in SUPPORTED_VNIC_TYPES:
            LOG.debug("Refusing to bind due to unsupported vnic_type: %s", vnic_type)
            return

        for segment in context.network.network_segments:
            if segment[api.NETWORK_TYPE] == p_const.TYPE_VXLAN:
                self._bind_port_segment(context, segment)
                return

    def _bind_port_segment(self, context: PortContext, segment):
        network_id = context.current["network_id"]
        mac_address = context.current["mac_address"]

        local_link_info = utils.local_link_from_binding_profile(
            context.current[portbindings.PROFILE]
        )
        vlan_group_name = self.ironic_client.baremetal_port_physical_network(
            local_link_info
        )

        if not vlan_group_name:
            LOG.error(
                "bind_port_segment: no physical_network found for baremetal "
                "port with mac address: %(mac)s",
                {"mac": mac_address},
            )
            return

        LOG.debug(
            "bind_port_segment: interface network %s vlan group %s",
            network_id,
            vlan_group_name,
        )

        current_vlan_segment = utils.vlan_segment_for_physnet(context, vlan_group_name)
        if current_vlan_segment:
            LOG.info(
                "vlan segment: %(segment)s already preset for physnet: " "%(physnet)s",
                {"segment": current_vlan_segment, "physnet": vlan_group_name},
            )
            dynamic_segment = current_vlan_segment
        else:
            dynamic_segment = context.allocate_dynamic_segment(
                segment={
                    "network_type": p_const.TYPE_VLAN,
                    "physical_network": vlan_group_name,
                },
            )

        LOG.debug("bind_port_segment: Native VLAN segment %s", dynamic_segment)

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

    def check_vlan_transparency(self, context):
        pass


def is_provisioning_network(network_id: str) -> bool:
    return network_id == cfg.CONF.ml2_understack.provisioning_network
