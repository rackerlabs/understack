"""HTTP client for the Kea Control Agent, used by the kea_proxy service."""

import socket
import threading
from urllib.parse import urlparse
from urllib.parse import urlunparse

import requests
from oslo_log import log as logging

from ironic_understack.conf import CONF

LOG = logging.getLogger(__name__)

# Serializes all reservation reads/writes across every request handled by
# this process. Correct only because kea_proxy runs as a single process
# (see components/ironic/kea-proxy-deploy.yaml) -- it does not coordinate
# across multiple replicas.
_lock = threading.Lock()


class KeaRequestError(Exception):
    """Raised when a request to a Kea Control Agent endpoint fails."""


def _lookup_api_urls():
    service_url = CONF.ironic_understack.kea_url
    parsed = urlparse(service_url)

    results = socket.getaddrinfo(parsed.hostname, None)
    ips = sorted({r[4][0] for r in results})

    return [urlunparse(parsed._replace(netloc=f"{ip}:{parsed.port}")) for ip in ips]


def _make_request(command, arguments, services=None):
    payload = {
        "command": command,
        "service": services or ["dhcp4"],
        "arguments": arguments,
    }

    max_retries = CONF.ironic_understack.kea_max_retries
    last_exception = None
    for attempt in range(max_retries):
        results = []
        try:
            for url in _lookup_api_urls():
                if CONF.ironic_understack.kea_log_requests:
                    LOG.debug(
                        "Sending %(command)s request to Kea API %(url)s",
                        {"command": command, "url": url},
                    )
                if CONF.ironic_understack.kea_log_requests_body:
                    LOG.debug(
                        "Sending %(command)s request body to Kea API"
                        " %(url)s: %(payload)s",
                        {"command": command, "url": url, "payload": payload},
                    )
                response = requests.post(
                    url,
                    json=payload,
                    timeout=CONF.ironic_understack.kea_request_timeout,
                )
                response.raise_for_status()
                results.append(response)
            return results[0].json()
        except requests.exceptions.Timeout as e:
            last_exception = e
            LOG.warning(
                "Timeout on attempt %d/%d for command %s",
                attempt + 1,
                max_retries,
                command,
            )
        except requests.exceptions.RequestException as e:
            last_exception = e
            LOG.warning(
                "Request failed on attempt %d/%d: %s",
                attempt + 1,
                max_retries,
                e,
            )

    LOG.error(
        "Failed to execute command %s after %d attempts: %s",
        command,
        max_retries,
        last_exception,
    )
    raise KeaRequestError(
        f"Failed to execute {command}: {last_exception}"
    ) from last_exception


def get_config():
    """Retrieve current Kea configuration."""
    return _make_request("config-get", {})[0]


def set_config(config):
    """Update Kea configuration."""
    return _make_request("config-set", config)


def save_config():
    """Save the current configuration to disk."""
    return _make_request("config-write", {})


def update_reservation(hw_address, client_class):
    """Create or update a host reservation for hw_address."""
    with _lock:
        config = get_config()
        config["arguments"].pop("hash", None)
        dhcp4_config = config["arguments"]["Dhcp4"]

        reservations = dhcp4_config.get("reservations", [])
        for reservation in reservations:
            if reservation.get("hw-address") == hw_address:
                reservation["client-classes"] = [client_class]
                break
        else:
            reservations.append(
                {"hw-address": hw_address, "client-classes": [client_class]}
            )
            dhcp4_config["reservations"] = reservations

        config["arguments"]["Dhcp4"] = dhcp4_config
        set_config(config["arguments"])
        save_config()


def delete_reservation(hw_address):
    """Remove a host reservation for hw_address, if one exists."""
    with _lock:
        config = get_config()
        config["arguments"].pop("hash", None)
        dhcp4_config = config["arguments"]["Dhcp4"]

        reservations = dhcp4_config.get("reservations", [])
        for reservation in reservations:
            if reservation.get("hw-address") == hw_address:
                LOG.debug("Removing reservation: %s", reservation)
                reservations.remove(reservation)
                break
        else:
            LOG.debug("No reservation found for %s", hw_address)
            return

        config["arguments"]["Dhcp4"] = dhcp4_config
        set_config(config["arguments"])
        save_config()


def get_leases(hw_address):
    """Retrieve IPv4/IPv6 lease addresses for hw_address."""
    addresses = []
    for command, service in [("lease4-get", "dhcp4"), ("lease6-get", "dhcp6")]:
        try:
            response = _make_request(
                command, {"hw-address": hw_address}, services=[service]
            )
            leases = response.get("arguments", {}).get("leases", [])
            if not leases:
                LOG.warning("No leases found for %s", hw_address)
            if service == "dhcp4":
                addresses.extend([lease["ip-address"] for lease in leases])
            else:
                for lease in leases:
                    addresses.extend(lease.get("ip-addresses", []))
        except KeaRequestError as e:
            LOG.warning(
                "Failed to fetch %s addresses for %s: %s", service, hw_address, e
            )
    return addresses
