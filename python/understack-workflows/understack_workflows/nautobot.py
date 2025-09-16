import logging
import sys
from uuid import UUID

import pynautobot
from pynautobot.core.api import Api as NautobotApi
from pynautobot.core.response import Record
from pynautobot.models import dcim


class NautobotRequestError(Exception):
    def __init__(self, e: pynautobot.RequestError):
        try:
            self._error_string = (
                f"Nautobot API ERROR {e.req.status_code} "
                f"for {e.base} {e.request_body}: {e.args[0]}"
            )
        except Exception:
            self._error_string = "Nautobot API ERROR"

    def __str__(self):
        """String form of the exception."""
        return self._error_string


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

    def device_by_id(self, device_id: UUID) -> dcim.Devices:
        device = self.session.dcim.devices.get(device_id)
        if not device:
            self.exit_with_error(f"Device {device_id!s} not found in Nautobot")
        return device  # type: ignore

    def interface_by_id(self, interface_id: UUID) -> dcim.Interfaces:
        interface = self.session.dcim.interfaces.get(interface_id)
        if not interface:
            self.exit_with_error(f"Interface {interface_id!s} not found in Nautobot")
        return interface  # type: ignore

    def non_lag_interface_by_mac(
        self, device_id: UUID, mac_address: str
    ) -> dcim.Interfaces:
        interface = self.session.dcim.interfaces.get(
            device_id=device_id,
            mac_address=mac_address,
            type__n="lag",
        )
        if not interface:
            self.exit_with_error(
                f"Interface with {device_id=} and {mac_address=} not found in Nautobot"
            )
        return interface  # type: ignore

    def tenancy_by_id(self, tenant_id: UUID) -> Record:
        if tenant_id:
            tenant = self.session.tenancy.tenants.get(id=tenant_id)
            if not tenant:
                self.logger.error("Tenant %s not found in Nautobot", tenant_id)
            return tenant  # type: ignore

    def update_cf(
        self,
        device_id: UUID,
        tenant_id: UUID | None = None,
        fields: dict[str, str] | None = None,
    ):
        device = self.device_by_id(device_id)
        if not device:
            raise Exception(f"No such device {device_id}")
        if not device.custom_fields:
            raise Exception(f"Device {device_id} has no custom fields")

        for field_name, field_value in (fields or {}).items():
            device.custom_fields[field_name] = field_value

        device.tenant = self.tenancy_by_id(tenant_id)  # type: ignore[attr-defined]

        response = device.save()
        self.logger.debug("save result: %s", response)
        return response

    def update_switch_interface_status(
        self, device_id: UUID, server_interface_mac: str, new_status: str
    ) -> dcim.Interfaces:
        """Change the Interface Status in Nautobot for interfaces.

        The device_id and interface MAC address parameters identify one or more
        server interfaces.

        Nautobot Interfaces that are selected that match the device UUID and MAC
        address, but excluding any parent LAG interfaces - only the member
        interfaces are considered.

        We then update ONE of the connected switch ports to the appropriate status.

        The interface is returned.
        """
        server_interface = self.non_lag_interface_by_mac(
            device_id, server_interface_mac
        )

        connected_endpoint = server_interface.connected_endpoint
        if not connected_endpoint:
            raise Exception(
                f"Interface {server_interface_mac=} {server_interface.type} "
                "is not connected in Nautobot"
            )
        switch_interface_id = connected_endpoint.id  # type: ignore
        self.logger.debug(
            "Interface server_interface_mac=%s connects to switch_interface_id=%s",
            server_interface_mac,
            switch_interface_id,
        )

        switch_interface = self.interface_by_id(switch_interface_id)
        switch_interface.status = new_status  # type: ignore
        result = switch_interface.save()

        self.logger.debug(
            "Interface switch_interface_id=%s updated to Status %s result=%s",
            switch_interface_id,
            new_status,
            result,
        )
        return switch_interface

    def update_device_status(self, device_id: UUID, device_status: str):
        device = self.device_by_id(device_id)
        device.status = device_status  # type: ignore
        result = device.save()
        self.logger.info(
            "device %s updated to Status %s result=%s", device_id, device_status, result
        )
        return result
