from dataclasses import dataclass
from dataclasses import field

from .link import Link


@dataclass
class Network:
    id: str
    ip_address: str
    netmask: str
    network_id: str
    link: Link
    type: str
    routes: list
    services: "list | None" = field(default=None)

    def default_routes(self):
        return [route for route in self.routes if route.is_default()]
