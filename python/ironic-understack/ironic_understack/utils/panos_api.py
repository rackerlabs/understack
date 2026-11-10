"""Minimal client for the PAN-OS XML API.

Credentials come from the ``[netdev_panos]`` oslo.config group; see
:mod:`ironic_understack.utils.netdev_credentials`.
"""

# Responses are only ever parsed from the appliance being managed, and the
# stdlib expat parser does not resolve external entities.
import xml.etree.ElementTree as ET

import requests
from oslo_log import log

from ironic_understack.conf import CONF
from ironic_understack.utils import netdev_credentials

LOG = log.getLogger(__name__)

TIMEOUT = 30

# Passwords are tried in this order. An appliance that has been through initial
# setup takes the standard password, one part way through takes preconfig, and
# a factory-fresh one still takes the factory default.
PASSWORD_ORDER = (
    ("standard", "standard_password"),
    ("preconfig", "preconfig_password"),
    ("factory", "factory_password"),
)


def _xml_to_dict(element: ET.Element) -> dict | str | list:
    """Convert an XML element tree to nested dicts/lists/strings.

    Handles the PAN-OS XML response format where repeated elements
    become lists and single elements become dicts.
    """
    children = list(element)
    if not children:
        # Leaf node - return the text content
        return (element.text or "").strip()

    # Group children by tag name
    grouped = {}
    for child in children:
        tag = child.tag
        if tag not in grouped:
            grouped[tag] = []
        grouped[tag].append(_xml_to_dict(child))

    # Convert single-element lists to scalars
    result = {}
    for tag, values in grouped.items():
        result[tag] = values[0] if len(values) == 1 else values

    return result


class PanosApiError(Exception):
    """The PAN-OS API rejected a request or returned an unusable response."""


class PanosClient:
    def __init__(self, address: str, session: requests.Session | None = None):
        self.address = address
        self.url = f"https://{address}/api/"
        self.session = session or requests.Session()
        self.session.verify = CONF.netdev_panos.verify_ssl
        self.api_key: str | None = None

    def login(self) -> str:
        """Obtain an API key, trying each configured password in turn.

        :returns: the label of the password that was accepted.
        :raises PanosApiError: if no configured password is accepted.
        """
        creds = netdev_credentials.get_panos_credentials()
        tried = []
        for label, key in PASSWORD_ORDER:
            password = creds[key]
            if not password:
                continue
            tried.append(label)
            api_key = self._keygen(creds["username"], password)
            if api_key:
                self.api_key = api_key
                return label
            LOG.debug("PAN-OS %s rejected the %s password", self.address, label)

        if not tried:
            raise PanosApiError("no PAN-OS passwords are configured in [netdev_panos]")
        raise PanosApiError(f"rejected the {', '.join(tried)} password(s)")

    def _keygen(self, username: str, password: str) -> str | None:
        # POST so the password is never part of a URL that might be logged.
        resp = self.session.post(
            self.url,
            data={"type": "keygen", "user": username, "password": password},
            timeout=TIMEOUT,
        )
        if resp.status_code == 403:
            return None
        key = _parse(resp).findtext("./result/key")
        if not key:
            raise PanosApiError("keygen response did not contain a key")
        return key

    def op(self, cmd: str) -> ET.Element:
        """Run an operational command and return its ``<result>`` element."""
        if self.api_key is None:
            raise PanosApiError("not logged in")
        resp = self.session.post(
            self.url,
            data={"type": "op", "cmd": cmd},
            headers={"X-PAN-KEY": self.api_key},
            timeout=TIMEOUT,
        )
        result = _parse(resp).find("result")
        if result is None:
            raise PanosApiError(f"no result for {cmd}")
        return result

    def system_info(self) -> dict[str, str]:
        """Return ``show system info`` as a flat dict of field name to value."""
        system = self.op("<show><system><info></info></system></show>").find("system")
        if system is None:
            raise PanosApiError("show system info returned no system element")
        return {child.tag: (child.text or "").strip() for child in system}

    def config(self, action: str, xpath: str, element: str | None = None) -> ET.Element:
        """Execute a config API command (set, edit, delete, get, show).

        :param action: Config action (set, edit, delete, get, show)
        :param xpath: XPath to the config element
        :param element: XML element string for set/edit actions
        :returns: The response result element
        """
        if self.api_key is None:
            raise PanosApiError("not logged in")

        params = {
            "type": "config",
            "key": self.api_key,
            "action": action,
            "xpath": xpath,
        }
        if element and action in ("set", "edit"):
            params["element"] = element

        resp = self.session.get(
            self.url,
            params=params,
            timeout=TIMEOUT,
        )
        root = _parse(resp)
        result = root.find("result")

        if result is None:
            # For delete/set operations, success response may not have a result
            return root
        return result

    def commit(self, description: str | None = None) -> str | None:
        """Commit configuration changes.

        :param description: Optional commit description
        :returns: Job ID or None if no changes to commit
        :raises PanosApiError: If commit fails
        """
        if self.api_key is None:
            raise PanosApiError("not logged in")

        # Log the commit with context about what's being committed
        import inspect

        caller = inspect.stack()[1]
        caller_func = caller.function
        caller_line = caller.lineno

        LOG.info(
            "PAN-OS %s: Committing config from %s:%d - %s",
            self.address,
            caller_func,
            caller_line,
            description or "no description",
        )

        cmd = "<commit></commit>"
        if description:
            cmd = f"<commit><description>{description}</description></commit>"

        resp = self.session.get(
            self.url,
            params={"type": "commit", "key": self.api_key, "cmd": cmd},
            timeout=120,
        )
        root = _parse(resp)

        # Find job ID first
        job = root.findtext(".//job") or root.findtext("result/job")

        # Check for "no changes to commit" (code 19 with specific message)
        if root.get("code") == "19":
            msg = root.findtext("msg") or ""
            if "no changes" in msg.lower():
                LOG.info("PAN-OS %s: No changes to commit", self.address)
                return None
        if not job:
            LOG.error(
                "PAN-OS %s commit response missing job ID. Root: %s",
                self.address,
                ET.tostring(root, encoding="unicode"),
            )
            raise PanosApiError("Could not find job ID in commit response")

        LOG.info("PAN-OS %s: Commit job %s started", self.address, job)
        return job

    def check_job(self, job_id: str) -> dict[str, str]:
        """Check the status of a commit job.

        :param job_id: Job ID from commit()
        :returns: Dict with status, result, progress, details
        """
        result = self.op(f"<show><jobs><id>{job_id}</id></jobs></show>")
        job = result.find("job")
        if job is None:
            return {
                "status": "unknown",
                "result": "unknown",
                "progress": "0",
                "details": "",
            }

        return {
            "status": job.findtext("status") or "unknown",
            "result": job.findtext("result") or "unknown",
            "progress": job.findtext("progress") or "0",
            "details": job.findtext("details") or "",
        }

    def wait_for_commit(self, job_id: str, timeout: int = 60) -> bool:
        """Wait for a commit job to complete.

        :param job_id: Job ID from commit()
        :param timeout: Max seconds to wait
        :returns: True if commit succeeded, False otherwise
        """
        import time

        for _ in range(timeout // 2):
            time.sleep(2)
            status = self.check_job(job_id)

            if status["status"] == "FIN":
                if status["result"] == "OK":
                    return True
                else:
                    LOG.error(
                        "PAN-OS %s commit failed: result=%s, details=%s",
                        self.address,
                        status["result"],
                        status.get("details", "No details available"),
                    )
                    return False

        LOG.error("PAN-OS %s commit timed out", self.address)
        return False

    def get_interface_macs(self) -> dict[str, str]:
        """Get MAC addresses for all interfaces.

        :returns: Dict mapping interface name to MAC address
        """
        result = self.op("<show><interface>all</interface></show>")
        macs = {}

        hw = result.find("hw")
        if hw is not None:
            for entry in hw.findall("entry"):
                name = entry.findtext("name")
                mac = entry.findtext("mac")
                if name and mac:
                    macs[name] = mac

        return macs

    def get_lldp_neighbors(self) -> list[dict[str, str]]:
        """Get LLDP neighbor information for all interfaces.

        :returns: List of dicts with keys: local_interface, chassis_id,
                  port_id, system_name
        """
        # Try both command formats
        result = None
        for cmd in [
            "<show><lldp><neighbors>all</neighbors></lldp></show>",
            "<show><lldp><neighbors/></lldp></show>",
        ]:
            try:
                result = self.op(cmd)
                break
            except PanosApiError:
                continue

        if result is None:
            return []

        # Convert XML to dict for easier parsing (same as panos.py script)
        result_dict = _xml_to_dict(result)

        # Extract entries - handle both single entry (dict) and multiple (list)
        entries = []
        if isinstance(result_dict, dict) and "entry" in result_dict:
            entry_data = result_dict["entry"]
            entries = entry_data if isinstance(entry_data, list) else [entry_data]

        neighbors = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue

            # Get local interface info
            local_info = entry.get("local", {})
            if not isinstance(local_info, dict):
                continue

            port_id = local_info.get("port-id", "")
            if not port_id:
                continue

            local_interface = f"ethernet1/{port_id}"

            # Get neighbor info
            neighbor_info = entry.get("neighbors", {})
            if not neighbor_info or neighbor_info == "":
                # No neighbor on this interface - skip it
                continue

            # neighbors contains an entry element
            if not isinstance(neighbor_info, dict):
                continue

            neighbor_entry = neighbor_info.get("entry", {})
            if not neighbor_entry or not isinstance(neighbor_entry, dict):
                continue

            neighbors.append(
                {
                    "local_interface": local_interface,
                    "chassis_id": neighbor_entry.get("chassis-id", ""),
                    "port_id": neighbor_entry.get("port-id", ""),
                    "system_name": neighbor_entry.get("system-name", ""),
                }
            )

        return neighbors

    def get_ha_status(self) -> dict[str, any]:
        """Get detailed High Availability status including peer information.

        :returns: Dict with keys:
            - enabled: "yes" or "no"
            - local: dict with state, version, mode, priority
            - peer: dict with state, conn_status, conn_ha1_up, conn_ha1_backup_up,
                    version, serial, mgmt_ip
            - group_id: HA group ID
            - error: error message if query fails
        """
        try:
            result = self.op(
                "<show><high-availability><all/></high-availability></show>"
            )

            status = {
                "enabled": result.findtext(".//enabled") or "no",
                "local": {
                    "state": (
                        result.findtext(".//local-info/state")
                        or result.findtext(".//group/local-info/state")
                        or "unknown"
                    ),
                    "version": result.findtext(".//local-info/build-rel") or "unknown",
                    "mode": result.findtext(".//local-info/mode") or "unknown",
                    "priority": result.findtext(".//local-info/priority") or "unknown",
                },
                "peer": {
                    "state": (
                        result.findtext(".//peer-info/state")
                        or result.findtext(".//group/peer-info/state")
                        or "unknown"
                    ),
                    "conn_status": result.findtext(".//peer-info/conn-status")
                    or "down",
                    "conn_ha1_up": (
                        result.findtext(".//peer-info/conn-ha1/conn-status") == "up"
                    ),
                    "conn_ha1_backup_up": (
                        result.findtext(".//peer-info/conn-ha1-backup/conn-status")
                        == "up"
                    ),
                    "version": result.findtext(".//peer-info/build-rel") or "unknown",
                    "serial": result.findtext(".//peer-info/serial-num") or "unknown",
                    "mgmt_ip": result.findtext(".//peer-info/mgmt-ip") or "unknown",
                },
                "group_id": result.findtext(".//group/group-id") or "unknown",
            }

            return status

        except Exception as e:
            return {"error": str(e), "enabled": "unknown"}

    def get_ha_interface_status(self) -> dict[str, dict[str, str]]:
        """Get operational status of HA interfaces.

        :returns: Dict mapping interface name (ha1-a, ha1-b, hsci) to status dict
                  with keys: state, speed, duplex
        """
        interfaces = {}

        for iface_name in ["ha1-a", "ha1-b", "hsci"]:
            try:
                result = self.op(f"<show><interface>{iface_name}</interface></show>")

                hw = result.find(".//hw")
                if hw is not None:
                    interfaces[iface_name] = {
                        "state": hw.findtext(".//state") or "unknown",
                        "speed": hw.findtext(".//speed") or "unknown",
                        "duplex": hw.findtext(".//duplex") or "unknown",
                    }
                else:
                    interfaces[iface_name] = {
                        "state": "not found",
                        "speed": "n/a",
                        "duplex": "n/a",
                    }

            except Exception as e:
                interfaces[iface_name] = {
                    "state": f"error: {e}",
                    "speed": "n/a",
                    "duplex": "n/a",
                }

        return interfaces

    def configure_ha(
        self,
        role: str,
        ha1_ip: str,
        ha1_backup_ip: str,
        ha2_ip: str,
        peer_ha1: str,
        peer_ha1_backup: str,
        priority: str,
        group_id: str = "1",
    ) -> bool:
        """Configure High Availability on the device.

        This method configures HA in multiple steps:
        1. Enable HA globally
        2. Configure HA interfaces (HA1, HA1-backup, HA2)
        3. Configure HA group settings (including peer-ip)
        4. Commit complete configuration

        Note: peer-ip must be set before committing, otherwise PAN-OS
        will reject the configuration with "HA1 peer-ip required".

        :param role: HA role ("primary" or "secondary") for logging purposes
        :param ha1_ip: IP address for HA1 interface (e.g., "10.2.2.1")
        :param ha1_backup_ip: IP address for HA1-backup interface
        :param ha2_ip: IP address for HA2 interface
        :param peer_ha1: Peer IP address for HA1 link
        :param peer_ha1_backup: Peer IP address for HA1-backup link
        :param priority: Device priority (lower = active, e.g., "50" for primary)
        :param group_id: HA group ID (default: "1")
        :returns: True if configuration succeeded, False otherwise
        """
        base_xpath = (
            "/config/devices/entry[@name='localhost.localdomain']"
            "/deviceconfig/high-availability"
        )

        try:
            # Step 1: Enable HA
            LOG.info("PAN-OS %s: Enabling HA", self.address)
            self.config("set", base_xpath, "<enabled>yes</enabled>")

            # Step 2: Configure HA interfaces
            LOG.info("PAN-OS %s: Configuring HA interfaces (%s)", self.address, role)

            # HA1
            ha1_xpath = f"{base_xpath}/interface/ha1"
            ha1_elem = (
                f"<ip-address>{ha1_ip}</ip-address>"
                f"<netmask>255.255.255.252</netmask>"
                f"<port>ha1-a</port>"
                f"<link-speed>auto</link-speed>"
                f"<link-duplex>auto</link-duplex>"
                f"<monitor-hold-time>3000</monitor-hold-time>"
            )
            self.config("set", ha1_xpath, ha1_elem)

            # HA1-backup
            ha1_backup_xpath = f"{base_xpath}/interface/ha1-backup"
            ha1_backup_elem = (
                f"<ip-address>{ha1_backup_ip}</ip-address>"
                f"<netmask>255.255.255.252</netmask>"
                f"<port>ha1-b</port>"
                f"<link-speed>auto</link-speed>"
                f"<link-duplex>auto</link-duplex>"
            )
            self.config("set", ha1_backup_xpath, ha1_backup_elem)

            # HA2
            ha2_xpath = f"{base_xpath}/interface/ha2"
            ha2_elem = (
                f"<ip-address>{ha2_ip}</ip-address>"
                f"<netmask>255.255.255.252</netmask>"
                f"<port>hsci</port>"
            )
            self.config("set", ha2_xpath, ha2_elem)

            # Step 3: Configure HA group (before committing anything)
            # Note: Must configure peer-ip before committing HA interfaces
            LOG.info("PAN-OS %s: Configuring HA group", self.address)
            group_xpath = f"{base_xpath}/group"

            # Group ID and peer IPs (MUST be set before first commit)
            self.config("set", group_xpath, f"<group-id>{group_id}</group-id>")
            self.config("set", group_xpath, f"<peer-ip>{peer_ha1}</peer-ip>")
            self.config(
                "set",
                group_xpath,
                f"<peer-ip-backup>{peer_ha1_backup}</peer-ip-backup>",
            )

            # Configuration synchronization
            self.config(
                "set",
                group_xpath,
                "<configuration-synchronization><enabled>yes</enabled>"
                "</configuration-synchronization>",
            )

            # Mode
            mode_elem = (
                "<mode>"
                "<active-passive>"
                "<passive-link-state>auto</passive-link-state>"
                "<monitor-fail-hold-down-time>1</monitor-fail-hold-down-time>"
                "</active-passive>"
                "</mode>"
            )
            self.config("set", group_xpath, mode_elem)

            # State synchronization
            state_sync_elem = (
                "<state-synchronization>"
                "<enabled>yes</enabled>"
                "<transport>ethernet</transport>"
                "<ha2-keep-alive>"
                "<enabled>yes</enabled>"
                "<threshold>10000</threshold>"
                "<action>log-only</action>"
                "</ha2-keep-alive>"
                "</state-synchronization>"
            )
            self.config("set", group_xpath, state_sync_elem)

            # Election options (without timers - may not be supported via API)
            election_elem = (
                "<election-option>"
                f"<device-priority>{priority}</device-priority>"
                "<preemptive>no</preemptive>"
                "</election-option>"
            )
            self.config("set", group_xpath, election_elem)

            # Try to set timers (may fail on some PAN-OS versions)
            try:
                self.config(
                    "set",
                    f"{group_xpath}/election-option",
                    "<timers><recommended>yes</recommended></timers>",
                )
            except PanosApiError as e:
                LOG.debug(
                    "PAN-OS %s: Could not set HA timers (may not be required): %s",
                    self.address,
                    e,
                )

            # Step 4: Commit complete HA configuration (interfaces + group)
            LOG.info(
                "PAN-OS %s: Committing complete HA configuration (%s)",
                self.address,
                role,
            )
            job_id = self.commit(f"HA Configuration - {role}")
            if job_id and not self.wait_for_commit(job_id, timeout=120):
                LOG.error("PAN-OS %s: Failed to commit HA configuration", self.address)
                return False

            LOG.info("PAN-OS %s: HA configuration completed successfully", self.address)
            return True

        except Exception as e:
            LOG.error("PAN-OS %s: HA configuration failed: %s", self.address, e)
            return False


def _parse(resp: requests.Response) -> ET.Element:
    try:
        root = ET.fromstring(resp.content)  # noqa: S314
    except ET.ParseError as e:
        raise PanosApiError(f"HTTP {resp.status_code}: response is not XML") from e
    if root.get("status") != "success":
        msg = " ".join(text.strip() for text in root.itertext() if text.strip())
        raise PanosApiError(f"HTTP {resp.status_code}: {msg or 'request failed'}")
    return root
