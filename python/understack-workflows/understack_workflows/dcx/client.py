import logging
from functools import cached_property

import requests

logger = logging.getLogger(__name__)


class DcxClient:
    def __init__(self, auth_token: str, api_url: str) -> None:
        """Simple read-only client for the DCX inventory API.

        The auth token is sent as the X-Auth-Token header and is never logged.
        """
        self.token = auth_token
        self.api_url = api_url.rstrip("/")

    @cached_property
    def client(self) -> requests.Session:
        session = requests.Session()
        session.headers = {"X-Auth-Token": self.token}
        return session

    def switch_ports(self, device_number: int | str) -> list[dict]:
        """Return the raw switch_port entries for a device.

        The response is a list of ``{"switch_port": {...}}`` objects.
        """
        url = f"{self.api_url}/devices/{device_number}/switch_ports"
        logger.info("Fetching DCX switch_ports for device %s", device_number)
        response = self.client.get(url)
        response.raise_for_status()
        return response.json()

    def location(self, device_number: int | str) -> dict:
        """Return the location record for a device (rack/space/data center).

        The response is a list; we return the single matching entry.
        """
        url = f"{self.api_url}/devices/locations_and_ports"
        logger.info("Fetching DCX location for device %s", device_number)
        response = self.client.get(url, params={"device_numbers": device_number})
        response.raise_for_status()
        records = response.json()
        if not records:
            raise ValueError(f"DCX returned no location for device {device_number}")
        return records[0]
