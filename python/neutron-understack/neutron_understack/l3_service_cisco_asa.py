# inspired from
# https://docs.openstack.org/neutron/latest/admin/config-router-flavor-ovn.html

from neutron.services.l3_router.service_providers import base
from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.plugins import directory
from oslo_config import cfg
from oslo_log import log as logging

from neutron_understack import config
from neutron_understack.cisco_asa import CiscoAsaAsdm

LOG = logging.getLogger(__name__)
config.register_l3_svc_cisco_asa_opts(cfg.CONF)


@registry.has_registry_receivers
class CiscoAsa(base.L3ServiceProvider):
    use_integrated_agent_scheduler = True

    def __init__(self, l3plugin):
        super().__init__(l3plugin)
        self.core_plugin = directory.get_plugin()

    @registry.receives(
        resources.ROUTER_INTERFACE,
        [events.AFTER_CREATE, events.AFTER_UPDATE, events.AFTER_DELETE],
    )
    def _process_router_interface_create(self, resource, event, trigger, payload):
        LOG.debug("router_interface_early %s %s", event, payload.metadata)
        router = payload.states[0] if len(payload.states) >= 1 else None
        context = payload.context
        port = payload.metadata.get("port")
        subnets = payload.metadata.get("subnets")
        LOG.debug(
            "router_interface_create1 %s / %s / %s / %s", router, context, port, subnets
        )
        LOG.debug(
            "router_interface_create2 %s / %s",
            event,
            payload.metadata,
        )

    @registry.receives(
        resources.ROUTER_GATEWAY,
        [events.AFTER_CREATE, events.AFTER_UPDATE, events.AFTER_DELETE],
    )
    def _process_router_gateway(self, resource, event, trigger, payload):
        LOG.debug("router_gateway_early %s %s", event, payload.metadata)

        LOG.debug(
            "router_gateway %s / %s / %s / %s",
            event,
            payload.metadata,
            payload.states[0],
            payload.states[1],
        )

    @registry.receives(resources.FLOATING_IP, [events.AFTER_UPDATE])
    def _process_floatingip_update(self, resource, event, trigger, payload):
        conf = cfg.CONF.l3_service_cisco_asa

        # read the state, state[0] is previous and state[1] is current
        context = payload.context
        # are we associating (True) or disassociating (False)
        assoc_disassoc = payload.metadata["association_event"]
        # associating we want the current state while disassociating
        # we want the previous
        fip = payload.states[1] if assoc_disassoc else payload.states[0]

        # what is the floating IP we are trying to use
        float_ip_addr = fip["floating_ip_address"]
        # what is the router ID
        router_id = fip["router_id"]
        # inside IP
        inside_ip_addr = fip["fixed_ip_address"]
        inside_port_info = fip["port_details"]
        asa_inside_inf = None
        asa_outside_inf = conf.outside_interface
        if inside_port_info:
            # we will use the UUID of the network as our internal interface name
            asa_inside_inf = inside_port_info["network_id"]

        # Since our network blocks need to be routed to the firewalls
        # explicitly we'll store information about which firewall in the
        # floating IP's network rather than the router object. The real
        # behavior should be that the router object maps to the firewall
        # but in this case the network is likely more correct. Plus
        # the network is 'external' and cannot be mucked with by a
        # normal user.
        LOG.debug(
            "Looking up floating IP's network (%s) description",
            fip["floating_network_id"],
        )
        if not fip["floating_network_id"]:
            return
        try:
            float_ip_net = self.core_plugin.get_network(
                context, fip["floating_network_id"], fields=["description"]
            )
        except Exception:
            LOG.exception(
                "Unable to lookup floating IP's network %s", fip["floating_network_id"]
            )
            return

        try:
            asa_mgmt = float_ip_net["description"].split("=")[-1]
        except Exception:
            LOG.exception(
                "Unable to parse firewall mgmt IP and port from floating IP "
                "network description"
            )
            return

        action_msg = "associate" if assoc_disassoc else "disassociate"

        LOG.debug(
            "Request to %s floating IP %s via router %s/%s/%s to %s on %s",
            action_msg,
            float_ip_addr,
            router_id,
            asa_mgmt,
            asa_outside_inf,
            inside_ip_addr,
            asa_inside_inf,
        )

        if asa_mgmt and asa_inside_inf and inside_ip_addr and float_ip_addr:
            asa = CiscoAsaAsdm(
                f"https://{asa_mgmt}", conf.username, conf.password, conf.user_agent
            )
            if assoc_disassoc:
                ret = asa.create_nat(
                    float_ip_addr, asa_outside_inf, inside_ip_addr, asa_inside_inf
                )
            else:
                ret = asa.delete_nat(inside_ip_addr)

            if not ret:
                LOG.error(
                    "Unable to make change on ASA device for router %s",
                    fip["router_id"],
                )
