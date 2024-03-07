from dataclasses import dataclass
from dataclasses import field


@dataclass
class PhysicalNic:
    id: str
    ethernet_mac_address: str
    type: str = "phy"
    mtu: int = 1500


@dataclass
class NetworkRoute:
    network: str
    netmask: str
    gateway: str


@dataclass
class BondedNic:
    id: str
    link: str
    ethernet_mac_address: str
    mtu: int = 1500
    type: str = "bond"
    bond_links: list[str] = field(default_factory=list)
    bond_mode: str = "802.1ad"
    bond_xmit_hash_policy: str = "layer3+4"
    bond_miimon: int | None = 100
    routes: list[NetworkRoute] = field(default_factory=list)


@dataclass
class Network:
    id: str | None = None
    network_id: str | None = None
    link: str | None = None
    type: str = "ipv4"
    ip_address: str | None = None
    netmask: str | None = None
    routes: list[NetworkRoute] = field(default_factory=list)


@dataclass
class Service:
    type: str
    address: str


@dataclass
class NetworkInfo:
    links: list[PhysicalNic | BondedNic] = field(default_factory=list)
    networks: list[Network] = field(default_factory=list)
    services: list[Service] = field(default_factory=list)
