import json
import subprocess
import sys
from dataclasses import dataclass
from functools import cached_property


@dataclass
class Link:
    ethernet_mac_address: str
    id: str
    mtu: int
    type: str
    vif_id: str


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
    services: list

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
        self.links = [Link(**link) for link in data.get("links", [])]
        self.networks = []

        for net_data in data.get("networks", []):
            net_data = net_data.copy()
            routes_data = net_data.pop("routes", [])
            routes = [Route(**route) for route in routes_data]
            link_id = net_data.pop("link", [])
            relevant_link = next(link for link in self.links if link.id == link_id)
            self.networks.append(Network(**net_data, routes=routes, link=relevant_link))

        self.services = [Service(**service) for service in data.get("services", [])]

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
        if self.dry_run:
            print(f"Executing: {cmd}")
        else:
            return subprocess.run(cmd, check=True)  # noqa: S603

    def configure_interfaces(self):
        for net in self.network_data.networks:
            if net.default_routes():
                # we handle the management interface differently
                continue
            nic = self.nics.find_by_mac(net.link.ethernet_mac_address)
            self._change_ip(nic.name, net.ip_address, net.netmask)

    def configure_management_interface(self):
        mgmt_network = next(
            net for net in self.network_data.networks if net.default_routes()
        )
        return self._change_ip("vmk0", mgmt_network.ip_address, mgmt_network.netmask)

    @cached_property
    def nics(self):
        return NICList()

    def _change_ip(self, interface, ip, netmask):
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
        if self.dry_run:
            print(f"Executing: {cmd}")
        else:
            subprocess.run(cmd, check=True)  # noqa: S603


###


def main(json_file, dry_run):
    network_data = NetworkData.from_json_file(json_file)
    esx = ESXConfig(network_data, dry_run=dry_run)
    esx.configure_management_interface()
    esx.configure_default_route()
    esx.configure_interfaces()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <json-file> [--dry-run]")
        sys.exit(1)

    try:
        main(sys.argv[1], sys.argv[2] == "--dry-run")
    except Exception as e:
        print(f"Error configuring network: {str(e)}")
        sys.exit(1)
