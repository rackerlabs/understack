from dataclasses import dataclass


@dataclass
class Route:
    gateway: str
    netmask: str
    network: str

    def is_default(self):
        return self.network == "0.0.0.0" and self.netmask == "0.0.0.0"
