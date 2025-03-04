from functools import cached_property

from .esxhost import ESXHost
from .network_data import NetworkData
from .nic import NIC
from .nic_list import NICList


class ESXConfig:
    def __init__(self, network_data: NetworkData, dry_run=False) -> None:
        self.network_data = network_data
        self.dry_run = dry_run
        self.host = ESXHost(dry_run)

    def add_default_mgmt_interface(
        self, portgroup_name, switch_name, interface_name="vmk0"
    ):
        self.host.portgroup_add(portgroup_name=portgroup_name, switch_name=switch_name)
        self.host.add_ip_interface(name=interface_name, portgroup_name=portgroup_name)

    def clean_default_network_setup(self, portgroup_name, switch_name):
        """Removes default networking setup left by the installer."""
        self.host.delete_vmknic(portgroup_name=portgroup_name)
        self.host.portgroup_remove(
            switch_name=switch_name, portgroup_name=portgroup_name
        )
        self.host.destroy_vswitch(name=switch_name)

    def configure_default_route(self):
        """Configures default route.

        If multiple default routes are present, only first one is used.
        """
        route = self.network_data.default_route()
        self.host.configure_default_route(route.gateway)

    def configure_portgroups(self, switch_name="vSwitch0"):
        portgroups = []
        for link in self.network_data.links:
            if link.type == "vlan":
                vid = link.vlan_id
                pg_name = f"internal_net_vid_{vid}"
                self.host.portgroup_add(portgroup_name=pg_name, switch_name=switch_name)
                self.host.portgroup_set_vlan(portgroup_name=pg_name, vlan_id=vid)
                portgroups.append(pg_name)
        return portgroups

    def configure_management_interface(self):
        mgmt_network = next(
            net for net in self.network_data.networks if net.default_routes()
        )
        return self.host.change_ip(
            "vmk0", mgmt_network.ip_address, mgmt_network.netmask
        )

    def configure_vswitch(self, uplink: NIC, switch_name: str, mtu: int):
        """Sets up vSwitch."""
        self.host.create_vswitch(switch_name)
        self.host.uplink_add(nic=uplink.name, switch_name=switch_name)
        self.host.vswitch_failover_uplinks(
            active_uplinks=[uplink.name], name=switch_name
        )
        self.host.vswitch_security(name=switch_name)
        self.host.vswitch_settings(mtu=mtu, name=switch_name)

    def configure_requested_dns(self):
        """Configures DNS servers that were provided in network_data.json."""
        dns_servers = [
            srv.address for srv in self.network_data.services if srv.type == "dns"
        ]
        if not dns_servers:
            return

        return self.host.configure_dns(servers=dns_servers)

    def identify_uplink(self) -> NIC:
        eligible_networks = [
            net for net in self.network_data.networks if net.default_routes()
        ]
        if len(eligible_networks) != 1:
            raise ValueError(
                "the network_data.json should only contain a single default route."
                "Unable to identify uplink interface"
            )
        link = eligible_networks[0].link
        return self.nics.find_by_mac(link.ethernet_mac_address)

    @cached_property
    def nics(self):
        return NICList()
