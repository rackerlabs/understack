import requests
import tenacity
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


def _retry_stop(retry_state):
    return retry_state.attempt_number >= CONF.ironic_understack.kea_max_retries


def _log_retry(retry_state):
    _self, method, path = retry_state.args[:3]
    LOG.warning(
        "Request to kea_proxy failed on attempt %d for %s %s: %s",
        retry_state.attempt_number,
        method,
        path,
        retry_state.outcome.exception(),
    )


class KeaDHCPApi(base.BaseDHCP):
    """Thin HTTP client for the kea_proxy service.

    All direct Kea Control Agent communication (endpoint discovery,
    retries, config read-modify-write, locking) lives in kea_proxy; this
    driver only talks to that proxy's REST API.
    """

    def __init__(self):
        super().__init__()

        if not CONF.ironic_understack.kea_proxy_url:
            raise DHCPConfigurationError(
                "kea_proxy_url must be specified in configuration"
            )

    @tenacity.retry(
        stop=_retry_stop,
        retry=tenacity.retry_if_exception_type(requests.exceptions.RequestException),
        before_sleep=_log_retry,
        reraise=True,
    )
    def _send(self, method, path, **kwargs):
        url = f"{CONF.ironic_understack.kea_proxy_url}{path}"
        response = requests.request(
            method,
            url,
            timeout=CONF.ironic_understack.kea_request_timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def _request(self, method, path, **kwargs):
        try:
            return self._send(method, path, **kwargs)
        except requests.exceptions.RequestException as e:
            LOG.error(
                "Failed to execute %s %s after %d attempts: %s",
                method,
                path,
                self._send.statistics.get("attempt_number"),
                e,
            )
            raise DHCPConfigurationError(
                f"Failed to execute {method} {path}: {e}"
            ) from e

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
