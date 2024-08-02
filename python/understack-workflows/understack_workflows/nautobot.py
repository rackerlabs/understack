import logging
import sys
from typing import Protocol

import pynautobot
from pynautobot.core.api import Api as NautobotApi
from pynautobot.models.dcim import Devices as NautobotDevice
from pynautobot.models.dcim import Interfaces as NautobotInterface


class Interface(Protocol):
    name: str
    mac_addr: str
    location: str


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

    def device(self, device_name: str) -> NautobotDevice:
        device = self.session.dcim.devices.get(name=device_name)
        if not device:
            self.exit_with_error(f"Device {device_name} not found in Nautobot")
        return device

    def device_oob_interface(
        self,
        device: NautobotDevice,
    ) -> NautobotInterface:
        oob_intf = self.session.dcim.interfaces.get(
            device_id=device.id, name=["iDRAC", "iLO"]
        )
        if not oob_intf:
            self.exit_with_error(
                f"No OOB interfaces found for {device.name} in Nautobot"
            )
        return oob_intf

    def ip_from_interface(self, interface: NautobotInterface) -> str:
        ips = interface.ip_addresses
        if not ips:
            self.exit_with_error(
                f"No IP addresses found for interface: {interface.name}"
            )
        return ips[0].host

    def device_oob_ip(self, device_name: str) -> str:
        device = self.device(device_name)
        oob_intf = self.device_oob_interface(device)
        oob_ip = self.ip_from_interface(oob_intf)
        return oob_ip

    def construct_interfaces_payload(
        self,
        interfaces: list[Interface],
        device_id: str,
        device_name: str,
    ) -> list[dict]:
        payload = []
        for interface in interfaces:
            nautobot_intf = self.session.dcim.interfaces.get(
                device_id=device_id, name=interface.name
            )
            if nautobot_intf is None:
                self.logger.info(
                    f"{interface.name} was NOT found for {device_name}, creating..."
                )
                payload.append(self.interface_payload_data(device_id, interface))
            else:
                self.logger.info(
                    f"{nautobot_intf.name} found in Nautobot for "
                    f"{device_name}, no action will be taken."
                )
        return payload

    def interface_payload_data(self, device_id: str, interface: Interface) -> dict:
        return {
            "device": device_id,
            "name": interface.name,
            "mac_address": interface.mac_addr,
            "type": "other",
            "status": "Active",
            "description": f"Location: {interface.location}",
        }

    def bulk_create_interfaces(
        self, device_name: str, interfaces: list[Interface]
    ) -> list[NautobotInterface] | None:
        device = self.device(device_name)
        payload = self.construct_interfaces_payload(interfaces, device.id, device.name)
        if payload:
            try:
                req = self.session.dcim.interfaces.create(payload)
            except pynautobot.core.query.RequestError as e:
                self.exit_with_error(e)

            for interface in req:
                self.logger.info(f"{interface.name} successfully created")

            return req
