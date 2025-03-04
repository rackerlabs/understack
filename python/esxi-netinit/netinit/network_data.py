import json

from .link import Link
from .network import Network
from .route import Route
from .service import Service


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
