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

        LOG.debug(
            "PAN-OS %s config %s: xpath=%s element=%s",
            self.address,
            action,
            xpath,
            element[:100] if element else None,
        )

        resp = self.session.get(
            self.url,
            params=params,
            timeout=TIMEOUT,
        )
        root = _parse(resp)
        result = root.find("result")

        LOG.debug(
            "PAN-OS %s config %s: status=%s, full response=%s",
            self.address,
            action,
            root.get("status"),
            ET.tostring(root, encoding="unicode")[:500],
        )

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

        cmd = "<commit></commit>"
        if description:
            cmd = f"<commit><description>{description}</description></commit>"

        LOG.debug(
            "PAN-OS %s committing: %s", self.address, description or "no description"
        )

        resp = self.session.get(
            self.url,
            params={"type": "commit", "key": self.api_key, "cmd": cmd},
            timeout=120,
        )
        root = _parse(resp)

        LOG.debug(
            "PAN-OS %s commit response: status=%s, code=%s, msg=%s, full_xml=%s",
            self.address,
            root.get("status"),
            root.get("code"),
            root.findtext("msg"),
            ET.tostring(root, encoding="unicode")[:800],
        )

        # Find job ID first
        job = root.findtext(".//job") or root.findtext("result/job")

        # Check for "no changes to commit" (code 19 with specific message)
        if root.get("code") == "19":
            msg = root.findtext("msg") or ""
            if "no changes" in msg.lower():
                LOG.debug(
                    "PAN-OS %s commit returned code 19 (no changes): %s",
                    self.address,
                    msg,
                )
                return None
            else:
                LOG.debug(
                    "PAN-OS %s commit returned code 19 but message doesn't "
                    "indicate 'no changes': %s",
                    self.address,
                    msg,
                )
        if not job:
            LOG.error(
                "PAN-OS %s commit response missing job ID. Root: %s",
                self.address,
                ET.tostring(root, encoding="unicode"),
            )
            raise PanosApiError("Could not find job ID in commit response")

        LOG.debug("PAN-OS %s commit started, job ID: %s", self.address, job)
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
                    LOG.debug("PAN-OS %s commit job %s succeeded", self.address, job_id)
                    return True
                else:
                    LOG.error(
                        "PAN-OS %s commit failed: %s", self.address, status["result"]
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
                LOG.debug(
                    "PAN-OS %s LLDP skipping entry - neighbor_entry invalid: %s",
                    self.address,
                    neighbor_entry,
                )
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


def _parse(resp: requests.Response) -> ET.Element:
    try:
        root = ET.fromstring(resp.content)  # noqa: S314
    except ET.ParseError as e:
        raise PanosApiError(f"HTTP {resp.status_code}: response is not XML") from e
    if root.get("status") != "success":
        msg = " ".join(text.strip() for text in root.itertext() if text.strip())
        raise PanosApiError(f"HTTP {resp.status_code}: {msg or 'request failed'}")
    return root
