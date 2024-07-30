import logging
import pynautobot
import requests
import sys
from pynautobot.core.api import Api as NautobotApi
from pynautobot.models.dcim import Devices as NautobotDevice


class Nautobot:
    def __init__(self, url, token, logger=None, session=None):
        self.url = url
        self.token = token
        self.logger = logger or logging.getLogger(__name__)
        self.session = session or self.api_session(self.url, self.token)

    def exit_with_error(self, error):
        self.logger.error(error)
        sys.exit(1)

    def api_session(self, url: str, token: str) -> NautobotApi:
        try:
            return pynautobot.api(url, token=token)
        except requests.exceptions.ConnectionError as e:
            self.exit_with_error(e)
        except pynautobot.core.query.RequestError as e:
            self.exit_with_error(e)

    def device_by_id(self, device_id: str) -> NautobotDevice:
        device = self.session.dcim.devices.get(device_id)
        if not device:
            self.exit_with_error(f"Device {device_id} not found in Nautobot")
        return device

    def device_interfaces(self, device_id: str):
        return self.session.dcim.interfaces.filter(device_id=device_id)

    def update_cf(self, device_id, field_name: str, field_value: str):
        device = self.device_by_id(device_id)
        device.custom_fields[field_name] = field_value
        response = device.save()
        self.logger.info(f"save result: {response}")
        return response

    def uplink_switches(self, device_id) -> list[str]:
        interfaces = self.device_interfaces(device_id)
        ids = set()
        for iface in interfaces:
            endpoint = iface.connected_endpoint
            if not endpoint:
                continue
            endpoint.full_details()
            self.logger.debug(f"{iface} connected device {iface.connected_endpoint.device} ")
            remote_switch = endpoint.device
            if not remote_switch:
                continue

            ids.add(remote_switch.id)

        return list(ids)
