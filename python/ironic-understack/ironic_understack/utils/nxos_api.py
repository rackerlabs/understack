"""Minimal read-only client for Cisco NX-API (JSON-RPC over HTTPS).

The switch needs ``feature nxapi``.
"""

import re

import requests
from oslo_log import log

LOG = log.getLogger(__name__)

TIMEOUT = 60

LLDP_CHASSIS_ID_SWITCH = re.compile(r"^\s*lldp chassis-id switch\s*$", re.MULTILINE)


class NxosApiError(Exception):
    """NX-API rejected a request or returned an unusable response."""


def rows(body: dict, table: str, row: str) -> list[dict]:
    """Return the rows of an NX-OS ``TABLE_x``/``ROW_x`` structure.

    NX-OS returns a lone row as a dict rather than a one-item list.
    """
    found = (body.get(table) or {}).get(row) or []
    return [found] if isinstance(found, dict) else list(found)


def normalize_mac(mac: str) -> str:
    """Turn NX-OS ``00de.fb12.3456`` (or any separator) into ``00:de:fb:12:34:56``."""
    digits = "".join(c for c in mac.lower() if c in "0123456789abcdef")
    if len(digits) != 12:
        raise ValueError(f"not a MAC address: {mac!r}")
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))


def parse_ethernet_interfaces(body: dict) -> list[dict[str, str]]:
    """Return each physical Ethernet interface's name and burned-in MAC.

    Takes ``show interface`` output. The burned-in (bia) address is used
    because the operational address of a routed port defaults to the shared
    system MAC. Interfaces that report no usable MAC are skipped.
    """
    found = []
    for row in rows(body, "TABLE_interface", "ROW_interface"):
        name = row.get("interface", "")
        if not name.startswith("Ethernet"):
            continue
        raw = row.get("eth_bia_addr") or row.get("eth_hw_addr")
        try:
            mac = normalize_mac(raw if isinstance(raw, str) else "")
        except ValueError:
            LOG.warning("No usable MAC for %s (%r)", name, raw)
            continue
        found.append({"interface": name, "mac": mac})
    return found


def parse_chassis_mac(body: dict) -> str | None:
    """Return the switch MAC from ``show vdc detail`` output, or None.

    LLDP sends it as the chassis ID when ``lldp chassis-id switch`` is
    configured. The default VDC (id 1) is preferred. Cisco does not document
    the field name, so ``vdc_mac`` and ``mac`` are tried before any other
    field ending in ``mac``.
    """
    vdcs = rows(body, "TABLE_vdc", "ROW_vdc")
    vdcs.sort(key=lambda row: str(row.get("vdc_id")) != "1")
    for row in vdcs:
        keys = ["vdc_mac", "mac", *sorted(k for k in row if k.endswith("mac"))]
        for key in keys:
            value = row.get(key)
            if not isinstance(value, str):
                continue
            try:
                return normalize_mac(value)
            except ValueError:
                continue
    return None


def parse_lldp_chassis_id(config: str) -> str:
    """Return what LLDP sends as the chassis ID: ``switch`` or ``interface``.

    Takes ``show running-config lldp`` text. ``switch`` when
    ``lldp chassis-id switch`` is configured (the switch MAC); otherwise
    ``interface``, the NX-OS default (each interface's MAC).
    """
    return "switch" if LLDP_CHASSIS_ID_SWITCH.search(config) else "interface"


class NxosClient:
    """Run ``show`` commands on a switch over NX-API.

    Only read-only commands are allowed, so callers cannot change the switch.
    Use it as a context manager so its HTTP session is closed.

    Anything the switch answered with, including an HTTP error page, is
    raised (or returned) as :class:`NxosApiError`; a
    :class:`requests.RequestException` means the switch was not reached.
    """

    def __init__(
        self,
        address: str,
        username: str,
        password: str,
        verify: bool | str = False,
        session: requests.Session | None = None,
    ):
        """:param verify: as for requests: a bool or a path to a CA bundle."""
        self.address = address
        self.url = f"https://{address}/ins"
        self.session = session or requests.Session()
        self.session.verify = verify
        self.session.auth = (username, password)

    def __enter__(self):
        """Use the client for a block; its session is closed on exit."""
        return self

    def __exit__(self, *exc):
        """Close the HTTP session."""
        self.close()

    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()

    def _run(self, commands: list[str], method: str) -> list[dict | NxosApiError]:
        """Send ``show`` commands in one JSON-RPC batch.

        :returns: each command's ``result``, or the :class:`NxosApiError` it
            failed with, in the order given.
        :raises NxosApiError: if the whole request was refused or unusable.
        :raises requests.RequestException: if the switch cannot be reached.
        """
        for command in commands:
            if not command.startswith("show "):
                raise ValueError(f"only show commands are allowed: {command!r}")
        payload = [
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": {"cmd": command, "version": 1},
                "id": n,
            }
            for n, command in enumerate(commands, start=1)
        ]
        resp = self.session.post(
            self.url,
            json=payload,
            headers={"Content-Type": "application/json-rpc"},
            timeout=TIMEOUT,
        )
        status = resp.status_code
        if status in (401, 403):
            raise NxosApiError(f"NX-API refused the credentials ({status})")
        try:
            data = resp.json()
        except ValueError as e:
            raise NxosApiError(f"HTTP {status}: response is not JSON") from e
        entries = data if isinstance(data, list) else [data]
        by_id = {str(e.get("id")): e for e in entries if isinstance(e, dict)}
        if len(commands) == 1 and len(by_id) == 1:
            # A lone answer belongs to the lone command, whatever its id says.
            by_id = {"1": next(iter(by_id.values()))}

        results: list[dict | NxosApiError] = []
        for n, command in enumerate(commands, start=1):
            entry = by_id.get(str(n))
            if entry is None:
                results.append(NxosApiError(f"{command!r}: no response"))
            elif error := entry.get("error"):
                detail = (error.get("data") or {}).get("msg") or error.get("message")
                results.append(NxosApiError(f"{command!r}: {detail}"))
            elif status >= 400:
                results.append(NxosApiError(f"{command!r}: HTTP {status}"))
            else:
                # Commands with no output (e.g. an empty table) return null.
                results.append(entry.get("result") or {})
        return results

    def show_many(self, commands: list[str]) -> list[dict | NxosApiError]:
        """Run ``show`` commands in one request; return each one's JSON output.

        A command that failed is returned as its :class:`NxosApiError` so the
        others are still usable.
        """
        return [
            r if isinstance(r, NxosApiError) else (r.get("body") or {})
            for r in self._run(commands, "cli")
        ]

    def show(self, command: str) -> dict:
        """Run one ``show`` command and return its structured (JSON) output."""
        (body,) = self.show_many([command])
        if isinstance(body, NxosApiError):
            raise body
        return body

    def show_text(self, command: str) -> str:
        """Run one ``show`` command and return its plain-text output.

        For commands without structured output, such as ``show running-config``.
        """
        (result,) = self._run([command], "cli_ascii")
        if isinstance(result, NxosApiError):
            raise result
        text = result.get("msg") or result.get("body") or ""
        if not isinstance(text, str):
            raise NxosApiError(f"{command!r}: expected text output, got {text!r}")
        return text

    def show_version(self) -> dict:
        return self.show("show version")
