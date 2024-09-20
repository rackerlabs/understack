from __future__ import annotations

from dataclasses import dataclass

from sushy import Sushy
from sushy.exceptions import ResourceNotFoundError
from sushy.resources.chassis.chassis import Chassis as SushyChassis
from sushy.resources.system.network.adapter import NetworkAdapter
from sushy.resources.system.network.port import NetworkPort


class ManufacturerNotSupported(Exception):
    pass


@dataclass
class NIC:
    name: str
    location: str
    interfaces: list[Interface]
    model: str

    @classmethod
    def from_redfish(cls, data: NetworkAdapter) -> NIC:
        location = cls.nic_location(data)
        nic = cls(data.identity, location, [], data.model)
        nic.interfaces = [Interface.from_redfish(i, nic) for i in cls.nic_ports(data)]
        return nic

    @classmethod
    def from_hp_json(cls, data: dict) -> NIC:
        nic = cls(data.get("name"), data.get("location"), [], data.get("name"))
        ports = data.get("network_ports") or data.get("unknown_ports")
        nic.interfaces = [Interface.from_hp_json(i, nic, ports) for i in ports]
        return nic

    @classmethod
    def nic_location(cls, nic: NetworkAdapter) -> str:
        try:
            return nic.json["Controllers"][0]["Location"]["PartLocation"][
                "ServiceLabel"
            ]
        except KeyError:
            return nic.identity

    @classmethod
    def nic_ports(cls, nic: NetworkAdapter) -> list[NetworkPort]:
        return nic.network_ports.get_members()


@dataclass
class Interface:
    name: str
    mac_addr: str
    location: str
    current_speed_mbps: int
    nic_model: str

    @classmethod
    def from_redfish(cls, data: NetworkPort, nic: NIC) -> Interface:
        if data.root.json["Vendor"] == "HPE":
            name = f"{nic.name}_{data.physical_port_number}"
            macaddr = data.associated_network_addresses[0]
        else:
            name = data.identity
            macaddr = cls.fetch_macaddr_from_sys_resource(data)
        return cls(
            name,
            macaddr,
            nic.location,
            data.current_link_speed_mbps,
            nic.model,
        )

    @classmethod
    def from_hp_json(cls, data: dict, nic: NIC, ports: list) -> Interface:
        p_num = data.get("port_num") or (ports.index(data) + 1)
        interface_name = f"NIC.{nic.location.replace(' ', '.')}_{p_num}"
        return cls(
            interface_name,
            data.get("mac_addr"),
            nic.location,
            data.get("speed", 0),
            nic.model,
        )

    @classmethod
    def fetch_macaddr_from_sys_resource(cls, data: NetworkPort) -> str:
        try:
            path = f"{data.root.get_system().ethernet_interfaces.path}/{data.identity}"
            macaddr = (
                data.root.get_system().ethernet_interfaces.get_member(path).mac_address
            )
        except ResourceNotFoundError:
            macaddr = ""
        return macaddr


@dataclass
class Systeminfo:
    asset_tag: str
    serial_number: str
    platform: str

    @classmethod
    def from_redfish(cls, chassis_data) -> Systeminfo:
        return cls(asset_tag=chassis_data.sku,
                   serial_number=chassis_data.serial_number,
                   platform=chassis_data.model)


@dataclass
class Chassis:
    name: str
    nics: list[NIC]
    network_interfaces: list[Interface]
    system_info: Systeminfo

    @classmethod
    def check_manufacturer(cls, manufacturer: str) -> None:
        supported_manufacturers = ["HPE", "Dell Inc."]
        if manufacturer not in supported_manufacturers:
            raise ManufacturerNotSupported(
                f"Manufacturer {manufacturer} not supported. "
                f"Supported manufacturers: {', '.join(supported_manufacturers)}"
            )

    @classmethod
    def bmc_is_ilo4(cls, chassis_data: SushyChassis) -> bool:
        return (
            chassis_data.redfish_version == "1.0.0"
            and chassis_data.manufacturer == "HPE"
        )

    @classmethod
    def from_redfish(cls, oob_obj: Sushy) -> Chassis:
        chassis_data = oob_obj.get_chassis(
            oob_obj.get_chassis_collection().members_identities[0]
        )

        cls.check_manufacturer(chassis_data.manufacturer)

        if cls.bmc_is_ilo4(chassis_data):
            return cls.from_hp_json(oob_obj, chassis_data.name)

        chassis = cls(chassis_data.name, [], [], [])
        chassis.nics = [
            NIC.from_redfish(i) for i in chassis_data.network_adapters.get_members()
        ]
        chassis.network_interfaces = cls.interfaces_from_nics(chassis.nics)
        chassis.system_info = Systeminfo.from_redfish(chassis_data)
        return chassis

    @classmethod
    def from_hp_json(cls, oob_obj: Sushy, chassis_name: str) -> Chassis:
        data = cls.chassis_hp_json_data(oob_obj)
        nics = [NIC.from_hp_json(i) for i in data]
        network_interfaces = cls.interfaces_from_nics(nics)
        return cls(chassis_name, nics, network_interfaces)

    @classmethod
    def interfaces_from_nics(cls, nics: list[NIC]) -> list[Interface]:
        return [interface for nic in nics for interface in nic.interfaces]

    @classmethod
    def chassis_hp_json_data(cls, oob_obj: Sushy) -> dict:
        oob_obj._conn.set_http_basic_auth(
            username=oob_obj._auth._username, password=oob_obj._auth._password
        )
        resp = oob_obj._conn.get(path="/json/comm_controller_info")
        resp.raise_for_status()
        data = resp.json()["comm_controllers"]
        return data
