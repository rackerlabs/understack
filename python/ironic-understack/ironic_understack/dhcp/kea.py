import socket
from urllib.parse import urlparse
from urllib.parse import urlunparse

import requests
from ironic import objects
from ironic.common import exception
from ironic.dhcp import base
from oslo_log import log as logging

from ironic_understack.conf import CONF

LOG = logging.getLogger(__name__)


class DHCPConfigurationError(exception.IronicException):
    """Raised when there is an error in configuring DHCP."""

    _msg_fmt = "DHCP configuration error: %(reason)s"


class KeaDHCPApi(base.BaseDHCP):
    def __init__(self):
        super().__init__()
        self.max_retries = CONF.ironic_understack.kea_max_retries

        if not CONF.ironic_understack.kea_url:
            raise DHCPConfigurationError("Kea URL must be specified in configuration")

    def _lookup_api_urls(self):
        service_url = CONF.ironic_understack.kea_url
        parsed = urlparse(service_url)

        results = socket.getaddrinfo(parsed.hostname, None)
        ips = sorted({r[4][0] for r in results})

        return [urlunparse(parsed._replace(netloc=f"{ip}:{parsed.port}")) for ip in ips]

    def _make_request(self, command, arguments, services=None):
        payload = {
            "command": command,
            "service": services or ["dhcp4"],
            "arguments": arguments,
        }

        last_exception = None
        for attempt in range(self.max_retries):
            results = []
            try:
                for url in self._lookup_api_urls():
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
                    self.max_retries,
                    command,
                )
            except requests.exceptions.RequestException as e:
                last_exception = e
                LOG.warning(
                    "Request failed on attempt %d/%d: %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                )

        LOG.error(
            "Failed to execute command %s after %d attempts: %s",
            command,
            self.max_retries,
            last_exception,
        )
        raise DHCPConfigurationError(
            f"Failed to execute {command}: {last_exception}"
        ) from last_exception

    def get_config(self):
        """Retrieve current Kea configuration."""
        return self._make_request("config-get", {})[0]

    def set_config(self, config):
        """Update Kea configuration."""
        return self._make_request("config-set", config)

    def get_statistics(self, name=None):
        """Retrieve DHCP server statistics."""
        if name:
            return self._make_request("statistic-get", {"name": name})
        return self._make_request("statistic-get-all", {})

    def _update_host_reservation(self, hw_address, boot_file_prefix=None, remove=False):
        """Modify a host reservation in the Kea config file or hosts database."""
        # TODO(cid) add support/replace with the host database configuration
        # option in a central database managed by Ironic; the commands to have
        # Kea manage it at runtime without restarting the server is a premium
        # offering
        try:
            config = self.get_config()
            config["arguments"].pop("hash", None)
            dhcp4_config = config["arguments"]["Dhcp4"]

            reservations = dhcp4_config.get("reservations", [])
            found = False
            for reservation in reservations:
                if reservation.get("hw-address") == hw_address:
                    if not remove:
                        reservation["client-classes"] = ["BOOTSRV_A"]
                    else:
                        LOG.debug("Removing reservation: %s", reservation)
                        reservations.remove(reservation)
                    found = True
                    break
            if not found:
                if not remove:
                    reservations.append(
                        {
                            "hw-address": hw_address,
                            "client-classes": ["BOOTSRV_A"],
                        }
                    )
                    dhcp4_config["reservations"] = reservations
                else:
                    LOG.debug("No reservation found in %s", reservations)
                    return True

            config["arguments"]["Dhcp4"] = dhcp4_config
            self.set_config(config["arguments"])
            return True
        except Exception as e:
            LOG.error("Failed to update reservation for %s: %s", hw_address, e)
            return False

    def update_port_dhcp_opts(self, port_id, dhcp_options, context=None):
        """Update DHCP options for a specific port in Kea."""
        port = objects.Port.get(context, port_id)

        for opt in dhcp_options:
            if opt["opt_name"] == "67":
                parsed_url = urlparse(opt["opt_value"])
                boot_file_prefix = f"{parsed_url.scheme}://{parsed_url.netloc}/"
        return self._update_host_reservation(port.address, boot_file_prefix)

    def update_dhcp_opts(self, task, options, vifs=None):
        """Update DHCP options for all ports associated with a node."""
        ports = vifs or task.ports
        success = True

        for port in ports:
            if not self.update_port_dhcp_opts(port.uuid, options):
                success = False
                LOG.error("Failed to update DHCP options for port %s", port.uuid)
        return success

    def clean_dhcp_opts(self, task):
        """Remove DHCP options for all ports associated with a node."""
        LOG.debug("Starting DHCP cleaning")
        success = True
        for port in task.ports:
            if not self._update_host_reservation(port.address, remove=True):
                success = False
                LOG.error("Failed to clean DHCP options for port %s", port.uuid)
        return success

    def get_ip_addresses(self, task):
        """Retrieve IP addresses for all ports associated to a node."""
        addresses = []
        for port in task.ports:
            for command, service in [("lease4-get", "dhcp4"), ("lease6-get", "dhcp6")]:
                try:
                    response = self._make_request(
                        command, {"hw-address": port.address}, services=[service]
                    )
                    leases = response.get("arguments", {}).get("leases", [])
                    if not leases:
                        LOG.warning("No leases found for port %s", port.address)
                    if service == "dhcp4":
                        addresses.extend([lease["ip-address"] for lease in leases])
                    else:
                        for lease in leases:
                            addresses.extend(lease.get("ip-addresses", []))
                except DHCPConfigurationError as e:
                    LOG.warning(
                        "Failed to fetch %s addresses for port %s: %s",
                        service,
                        port.address,
                        e,
                    )
        return addresses

    def supports_ipxe_tag(self):
        """Indicate whether the provider supports the 'ipxe' tag."""
        return False
