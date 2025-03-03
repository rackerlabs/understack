from dataclasses import dataclass
from dataclasses import field


@dataclass
class Link:
    ethernet_mac_address: str
    id: str
    mtu: int
    type: str
    vif_id: str
    vlan_id: "int | None" = field(default=None)
    vlan_mac_address: "str | None" = field(default=None)
    vlan_link: "Link | None" = field(default=None)
