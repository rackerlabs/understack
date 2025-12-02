from dataclasses import dataclass


@dataclass
class InspectedPort:
    """Represents a parsed entry from Ironic inspection (inventory) data."""

    mac_address: str
    name: str
    switch_system_name: str
    switch_port_id: str
    switch_chassis_id: str

    @property
    def local_link_connection(self) -> dict:
        return {
            "port_id": self.switch_port_id,
            "switch_id": self.switch_chassis_id,
            "switch_info": self.switch_system_name,
        }

    @property
    def parsed_name(self) -> dict[str, str]:
        parts = self.switch_system_name.split(".", maxsplit=1)
        if len(parts) != 2:
            raise ValueError(
                "Failed to parse switch hostname - expecting name.dc in %s", self
            )
        switch_name, data_center_name = parts

        parts = switch_name.rsplit("-", maxsplit=1)
        if len(parts) != 2:
            raise ValueError(
                f"Unknown switch name format: {switch_name} - this hook requires "
                f"that switch names follow the convention <cabinet-name>-<suffix>"
            )

        rack_name, switch_suffix = parts

        return {
            "rack_name": rack_name,
            "switch_suffix": switch_suffix,
            "data_center_name": data_center_name,
        }

    @property
    def rack_name(self) -> str:
        return self.parsed_name["rack_name"]

    @property
    def switch_suffix(self) -> str:
        return self.parsed_name["switch_suffix"]

    @property
    def data_center_name(self) -> str:
        return self.parsed_name["data_center_name"]
