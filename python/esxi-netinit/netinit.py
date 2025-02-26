import json
import subprocess
import sys
from dataclasses import dataclass
from dataclasses import field
from functools import cached_property


@dataclass
class Link:
    ethernet_mac_address: str
    id: str
    mtu: int
    type: str
    vif_id: str
    vlan_id: int | None = field(default=None)
    vlan_mac_address: str | None = field(default=None)
    vlan_link: "Link | None" = field(default=None)


@dataclass
class Route:
    gateway: str
    netmask: str
    network: str

    def is_default(self):
        return self.network == "0.0.0.0" and self.netmask == "0.0.0.0"


@dataclass
class Network:
    id: str
    ip_address: str
    netmask: str
    network_id: str
    link: Link
    type: str
    routes: list
    services: list | None = field(default=None)

    def default_routes(self):
        return [route for route in self.routes if route.is_default()]


@dataclass
class Service:
    address: str
    type: str


class NetworkData:
    """Represents network_data.json."""

    def __init__(self, data: dict) -> None:
        self.data = data
        self.links = self._init_links(data.get("links", []))
        self.networks = []

        for net_data in data.get("networks", []):
            net_data = net_data.copy()
            routes_data = net_data.pop("routes", [])
            routes = [Route(**route) for route in routes_data]
            link_id = net_data.pop("link", [])
            try:
                relevant_link = next(link for link in self.links if link.id == link_id)
            except StopIteration:
                raise ValueError(
                    f"Link {link_id} is not defined in links section"
                ) from None
            self.networks.append(Network(**net_data, routes=routes, link=relevant_link))

        self.services = [Service(**service) for service in data.get("services", [])]

    def _init_links(self, links_data):
        links_data = links_data.copy()
        links = []
        for link in links_data:
            if "vlan_link" in link:
                phy_link = next(
                    plink for plink in links if plink.id == link["vlan_link"]
                )
                link["vlan_link"] = phy_link

            links.append(Link(**link))
        return links

    def default_route(self) -> Route:
        return next(
            network.default_routes()[0]
            for network in self.networks
            if network.default_routes()
        )

    @staticmethod
    def from_json_file(path):
        with open(path) as f:
            data = json.load(f)
            return NetworkData(data)


@dataclass
class NIC:
    name: str
    status: str
    link: str
    mac: str


class NICList:
    def __init__(self, data=None) -> None:
        self.nics = NICList.parse(data or self._esxi_nics())

    @staticmethod
    def parse(data):
        output = []
        for line in data.split("\n"):
            if line.startswith("vmnic"):
                parts = line.split()
                nic = NIC(name=parts[0], status=parts[3], link=parts[4], mac=parts[7])
                output.append(nic)
        return output

    def _esxi_nics(self) -> str:
        return subprocess.run(  # noqa: S603
            [
                "/bin/esxcli",
                "network",
                "nic",
                "list",
            ],
            check=True,
            capture_output=True,
        ).stdout.decode()

    def find_by_mac(self, mac) -> NIC:
        return next(nic for nic in self.nics if nic.mac == mac)


class ESXConfig:
    def __init__(self, network_data: NetworkData, dry_run=False) -> None:
        self.network_data = network_data
        self.dry_run = dry_run

    def __execute(self, cmd: list[str]):
        if self.dry_run:
            print(f"Would exececute: {' '.join(cmd)}")
            return cmd
        else:
            subprocess.run(cmd, check=True)  # noqa: S603

    def configure_default_route(self):
        """Configures default route.

        If multiple default routes are present, only first one is used.
        """
        route = self.network_data.default_route()
        cmd = [
            "/bin/esxcli",
            "network",
            "ip",
            "route",
            "ipv4",
            "add",
            "-g",
            route.gateway,
            "-n",
            "default",
        ]
        return self.__execute(cmd)

    def configure_portgroups(self):
        for link in self.network_data.links:
            if link.type == "vlan":
                vid = link.vlan_id
                pg_name = f"internal_net_vid_{vid}"
                self.portgroup_add(portgroup_name=pg_name)
                self.portgroup_set_vlan(portgroup_name=pg_name, vlan_id=vid)

    def configure_management_interface(self):
        mgmt_network = next(
            net for net in self.network_data.networks if net.default_routes()
        )
        return self._change_ip("vmk0", mgmt_network.ip_address, mgmt_network.netmask)

    def portgroup_add(self, portgroup_name, switch_name="vswitch0"):
        """Adds Portgroup to a vSwitch."""
        cmd = [
            "/bin/esxcli",
            "network",
            "vswitch",
            "standard",
            "portgroup",
            "add",
            "--portgroup-name",
            str(portgroup_name),
            "--vswitch-name",
            str(switch_name),
        ]
        return self.__execute(cmd)

    def portgroup_set_vlan(self, portgroup_name, vlan_id):
        """Configures VLANid to be used on a portgroup."""
        cmd = [
            "/bin/esxcli",
            "network",
            "vswitch",
            "standard",
            "portgroup",
            "set",
            "--portgroup-name",
            str(portgroup_name),
            "--vlan-id",
            str(vlan_id),
        ]
        return self.__execute(cmd)

    @cached_property
    def nics(self):
        return NICList()

    def _change_ip(self, interface, ip, netmask):
        """Configures IP address on logical interface."""
        cmd = [
            "/bin/esxcli",
            "network",
            "ip",
            "interface",
            "ipv4",
            "set",
            "-i",
            interface,
            "-I",
            ip,
            "-N",
            netmask,
            "-t",
            "static",
        ]
        return self.__execute(cmd)

    def create_vswitch(self, name="vSwitch0", ports=256):
        """Creates vSwitch."""
        cmd = [
            "/bin/esxcli",
            "network",
            "vswitch",
            "standard",
            "add",
            "--ports",
            str(ports),
            "--vswitch-name",
            str(name),
        ]
        return self.__execute(cmd)

    def uplink_add(self, nic, switch_name="vSwitch0"):
        """Adds uplink to a vSwitch."""
        cmd = [
            "/bin/esxcli",
            "network",
            "vswitch",
            "standard",
            "uplink",
            "add",
            "--uplink-name",
            str(nic),
            "--vswitch-name",
            str(switch_name),
        ]
        return self.__execute(cmd)

    def vswitch_settings(self, mtu=9000, cdp="listen", name="vSwitch0"):
        cmd = [
            "/bin/esxcli",
            "network",
            "vswitch",
            "standard",
            "set",
            "--mtu",
            str(mtu),
            "--cdp-status",
            cdp,
            "--vswitch-name",
            str(name),
        ]
        return self.__execute(cmd)

    def vswitch_failover_uplinks(
        self, active_uplinks=None, standby_uplinks=None, name="vSwitch0"
    ):
        cmd = [
            "/bin/esxcli",
            "network",
            "vswitch",
            "standard",
            "policy",
            "failover",
            "set",
        ]

        if active_uplinks:
            cmd.extend(["--active-uplinks", ",".join(active_uplinks)])
        if standby_uplinks:
            cmd.extend(["--standby-uplinks", ",".join(standby_uplinks)])

        cmd.extend(
            [
                "--vswitch-name",
                str(name),
            ]
        )
        return self.__execute(cmd)

    def vswitch_security(
        self,
        allow_forged_transmits="no",
        allow_mac_change="no",
        allow_promiscuous="no",
        name="vSwitch0",
    ):
        cmd = [
            "/bin/esxcli",
            "network",
            "vswitch",
            "standard",
            "policy",
            "security",
            "set",
            "--allow-forged-transmits",
            allow_forged_transmits,
            "--allow-mac-change",
            allow_mac_change,
            "--allow-promiscuous",
            allow_promiscuous,
            "--vswitch-name",
            str(name),
        ]
        return self.__execute(cmd)

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

    def configure_vswitch(self, uplink: NIC, switch_name: str, mtu: int):
        """Sets up vSwitch."""
        self.create_vswitch(switch_name)
        self.uplink_add(nic=uplink.name, switch_name=switch_name)
        self.vswitch_failover_uplinks(active_uplinks=[uplink.name], name=switch_name)
        self.vswitch_security(name=switch_name)
        self.vswitch_settings(mtu=mtu, name=switch_name)


def main(json_file, dry_run):
    network_data = NetworkData.from_json_file(json_file)
    esx = ESXConfig(network_data, dry_run=dry_run)
    esx.configure_management_interface()
    esx.configure_default_route()
    esx.configure_vswitch(
        uplink=esx.identify_uplink(), switch_name="vSwitch0", mtu=9000
    )
    esx.configure_portgroups()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <json-file> [--dry-run]")
        sys.exit(1)

    try:
        main(sys.argv[1], sys.argv[2] == "--dry-run")
    except Exception as e:
        print(f"Error configuring network: {str(e)}")
        sys.exit(1)
