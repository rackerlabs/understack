import logging
import pynautobot
import requests
import sys
from typing import Protocol
from pynautobot.core.api import Api as NautobotApi
from pynautobot.models.dcim import Devices as NautobotDevice

class Nautobot:
    ALLOWED_STATUSES = [
        "enroll",
        "verifying",
        "manageable",
        "inspecting",
        "inspect wait",
        "inspect failed",
        "cleaning",
        "clean wait",
        "available",
        "deploying",
        "wait call-back",
        "deploy failed",
        "active",
        "deleting",
        "error",
        "adopting",
        "rescuing",
        "rescue wait",
        "rescue failed",
        "rescue",
        "unrescuing",
        "unrescue failed",
        "servicing",
        "service wait",
        "service failed",
    ]
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

    def update_status(self, device_id, new_status: str):
        device = self.device_by_id(device_id)

        if new_status not in self.ALLOWED_STATUSES:
            raise Exception(f"Status {new_status} for device {device_id} is not in ALLOWED_STATUSES.")

        device.custom_fields['ironic_provisioning_status'] = new_status
        response = device.save()
        print(f"save result: {response}")
        return response
