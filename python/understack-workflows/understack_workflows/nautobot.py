import logging
import sys
from typing import Protocol
from uuid import UUID

import pynautobot
from pynautobot.core.api import Api as NautobotApi
from pynautobot.models.dcim import Devices as NautobotDevice
from pynautobot.models.dcim import Interfaces as NautobotInterface


class Interface(Protocol):
    name: str
    mac_addr: str
    location: str


class Systeminfo(Protocol):
    asset_tag: str
    serial_number: str
    platform: str


class Nautobot:
    def __init__(self, url, token, logger=None, session=None):
        """Initialize our Nautobot API wrapper."""
        self.url = url
        self.token = token
        self.logger = logger or logging.getLogger(__name__)
        self.session = session or self.api_session(self.url, self.token)

    def exit_with_error(self, error):
        self.logger.error(error)
        sys.exit(1)

    def api_session(self, url: str, token: str) -> NautobotApi:
        return pynautobot.api(url, token=token)

    def device_oob_interface(
        self,
        device_id: UUID,
    ) -> NautobotInterface:
        oob_intf = self.session.dcim.interfaces.get(
            device_id=device_id, name=["iDRAC", "iLO"]
        )
        if not oob_intf:
            self.exit_with_error(
                f"No OOB interfaces found for device {device_id!s} in Nautobot"
            )
        return oob_intf

    def ip_from_interface(self, interface: NautobotInterface) -> str:
        ips = interface.ip_addresses
        if not ips:
            self.exit_with_error(
                f"No IP addresses found for interface: {interface.name}"
            )
        return ips[0].host

    def device_oob_ip(self, device_id: UUID) -> str:
        oob_intf = self.device_oob_interface(device_id)
        oob_ip = self.ip_from_interface(oob_intf)
        return oob_ip

    def construct_interfaces_payload(
        self,
        interfaces: list[Interface],
        device_id: UUID,
    ) -> list[dict]:
        payload = []
        for interface in interfaces:
            nautobot_intf = self.session.dcim.interfaces.get(
                device_id=device_id, name=interface.name
            )
            if nautobot_intf is None:
                self.logger.info(
                    f"{interface.name} was NOT found for device {device_id!s}, "
                    f"creating..."
                )
                payload.append(self.interface_payload_data(device_id, interface))
            else:
                self.logger.info(
                    f"{nautobot_intf.name} found in Nautobot for "
                    f"device {device_id!s}, no action will be taken."
                )
        return payload

    def interface_payload_data(self, device_id: UUID, interface: Interface) -> dict:
        return {
            "device": str(device_id),
            "name": interface.name,
            "mac_address": interface.mac_addr,
            "type": "other",
            "status": "Active",
            "description": f"Location: {interface.location}",
        }

    def bulk_create_interfaces(
        self, device_id: UUID, interfaces: list[Interface]
    ) -> list[NautobotInterface] | None:
        payload = self.construct_interfaces_payload(interfaces, device_id)
        if payload:
            try:
                req = self.session.dcim.interfaces.create(payload)
            except pynautobot.core.query.RequestError as e:
                self.exit_with_error(e)

            for interface in req:
                self.logger.info(f"{interface.name} successfully created")

            return req

    def device_by_id(self, device_id: UUID) -> NautobotDevice:
        device = self.session.dcim.devices.get(device_id)
        if not device:
            self.exit_with_error(f"Device {device_id!s} not found in Nautobot")
        return device

    def interface_by_id(self, interface_id: UUID) -> NautobotInterface:
        interface = self.session.dcim.interfaces.get(interface_id)
        if not interface:
            self.exit_with_error(f"Interface {interface_id!s} not found in Nautobot")
        return interface

    def non_lag_interface_by_mac(self, device_id: UUID, mac_address: str) -> list[NautobotInterface]:
        interfaces = self.session.dcim.interfaces.filter(
            device_id=device_id,
            mac_address=mac_address,
            type__n = "lag",
        )
        if not interfaces:
            self.exit_with_error(
                f"Interface with {device_id=} and {mac_address=} not found in Nautobot"
            )
        return interfaces[0]

    def device_interfaces(self, device_id: UUID):
        return self.session.dcim.interfaces.filter(device_id=device_id)

    def update_cf(self, device_id: UUID, field_name: str, field_value: str):
        device = self.device_by_id(device_id)
        device.custom_fields[field_name] = field_value
        response = device.save()
        self.logger.info(f"save result: {response}")
        return response

    def update_switch_interface_status(
        self, device_id: UUID, server_interface_mac: str, new_status: str
    ) -> NautobotInterface:
        """Change the Interface Status in Nautobot for interfaces

        The device_id and interface MAC address parameters identify one or more
        server interfaces.

        Nautobot Interfaces that are selected that match the device UUID and MAC
        address, but excluding any parent LAG interfaces - only the member
        interfaces are considered.

        We then update ONE of the connected switch ports to the appropriate status.

        The interface is returned.
        """
        server_interface = self.non_lag_interface_by_mac(device_id, server_interface_mac)

        connected_endpoint = server_interface.connected_endpoint
        if not connected_endpoint:
            raise Exception(
                f"Interface {server_interface_mac} {server_interface.type} not connected in Nautobot"
            )
        switch_interface_id = connected_endpoint.id
        self.logger.debug(
            f"Interface {server_interface_mac} connects to {switch_interface_id}"
        )

        switch_interface = self.interface_by_id(switch_interface_id)
        switch_interface.status = new_status
        result = switch_interface.save()

        self.logger.debug(
            f"Interface {switch_interface_id} updated to Status {new_status} {result=}"
        )
        return switch_interface

    def update_device_status(self, device_id: UUID, device_status: str):
        device = self.device_by_id(device_id)
        device.status = device_status
        result = device.save()
        self.logger.info(
            f"device {device_id} updated to Status {device_status} {result=}"
        )
        return result

    def uplink_switches(self, device_id: UUID) -> list[str]:
        interfaces = self.device_interfaces(device_id)
        ids = set()
        for iface in interfaces:
            endpoint = iface.connected_endpoint
            if not endpoint:
                continue
            endpoint.full_details()
            self.logger.debug(
                f"{iface} connected device {iface.connected_endpoint.device} "
            )
            remote_switch = endpoint.device
            if not remote_switch:
                continue

            ids.add(remote_switch.id)

        return list(ids)

    def update_system_info(self, device_id: UUID, system_info: Systeminfo):
        device = self.device_by_id(device_id)
        device.serial = system_info.serial_number
        device.platform = system_info.platform
        device.asset_tag = system_info.asset_tag
        response = device.save()
        self.logger.info(f"save result: {response}")
        return response
