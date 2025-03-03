from dataclasses import dataclass


@dataclass
class NIC:
    name: str
    status: str
    link: str
    mac: str
