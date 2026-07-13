import requests
from ironic import objects
from ironic.common import exception
from ironic.dhcp import base
from oslo_log import log as logging

from ironic_understack.conf import CONF

LOG = logging.getLogger(__name__)

DEFAULT_CLIENT_CLASS = "BOOTSRV_A"


class DHCPConfigurationError(exception.IronicException):
    """Raised when there is an error in configuring DHCP."""

    _msg_fmt = "DHCP configuration error: %(reason)s"


class KeaDHCPApi(base.BaseDHCP):
    """Thin HTTP client for the kea_proxy service.

    All direct Kea Control Agent communication (endpoint discovery,
    retries, config read-modify-write, locking) lives in kea_proxy; this
    driver only talks to that proxy's REST API.
    """

    def __init__(self):
        super().__init__()
        self.max_retries = CONF.ironic_understack.kea_max_retries

        if not CONF.ironic_understack.kea_proxy_url:
            raise DHCPConfigurationError(
                "kea_proxy_url must be specified in configuration"
            )

    def _request(self, method, path, **kwargs):
        url = f"{CONF.ironic_understack.kea_proxy_url}{path}"

        last_exception = None
        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    timeout=CONF.ironic_understack.kea_request_timeout,
                    **kwargs,
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.Timeout as e:
                last_exception = e
                LOG.warning(
                    "Timeout on attempt %d/%d for %s %s",
                    attempt + 1,
                    self.max_retries,
                    method,
                    url,
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
            "Failed to execute %s %s after %d attempts: %s",
            method,
            url,
            self.max_retries,
            last_exception,
        )
        raise DHCPConfigurationError(
            f"Failed to execute {method} {url}: {last_exception}"
        ) from last_exception

    def update_port_dhcp_opts(self, port_id, dhcp_options, context=None):
        """Update DHCP options for a specific port in Kea."""
        port = objects.Port.get(context, port_id)

        try:
            self._request(
                "POST",
                "/v1/update_reservation",
                json={
                    "hw-address": port.address,
                    "client_class": DEFAULT_CLIENT_CLASS,
                },
            )
            return True
        except DHCPConfigurationError as e:
            LOG.error("Failed to update reservation for %s: %s", port.address, e)
            return False

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
            try:
                self._request(
                    "DELETE",
                    "/v1/leases",
                    json={"hw-address": port.address},
                )
            except DHCPConfigurationError as e:
                success = False
                LOG.error("Failed to clean DHCP options for port %s: %s", port.uuid, e)
        return success

    def get_ip_addresses(self, task):
        """Retrieve IP addresses for all ports associated to a node."""
        addresses = []
        for port in task.ports:
            try:
                response = self._request(
                    "GET", "/v1/leases", params={"mac": port.address}
                )
                addresses.extend(response.get("addresses", []))
            except DHCPConfigurationError as e:
                LOG.warning(
                    "Failed to fetch addresses for port %s: %s", port.address, e
                )
        return addresses

    def supports_ipxe_tag(self):
        """Indicate whether the provider supports the 'ipxe' tag."""
        return False
