"""Port-channel naming for bonded baremetal ports.

The number is computed statelessly from the anchor interface alone:

    po = 1000 + port * 10 + D

where D is the breakout lane (1-4, or 0 when absent) plus 0 for the first
switch of a pair or 5 for the second. Only fixed-form leaves (slot 1) are
supported. The lowest possible number is 1010, so Po1000-1009 stay reserved.
"""

import re

from neutron_lib import exceptions as exc

MAX_PORT = 308
MAX_LANE = 4
SECOND_SWITCH_OFFSET = 5

_INTERFACE_RE = re.compile(
    r"^(?:eth(?:ernet)?)?\s*(?P<slot>\d+)/(?P<port>\d+)(?:/(?P<lane>\d+))?$",
    re.IGNORECASE,
)


class InvalidLagAnchor(exc.InvalidInput):
    message = "Cannot derive a port-channel name from interface %(port_id)r: %(why)s"


def lag_name(port_id: str, second_switch: bool = False) -> str:
    """Return the port-channel name (e.g. ``Po1170``) for an anchor interface."""
    match = _INTERFACE_RE.match(port_id.strip())
    if not match:
        raise InvalidLagAnchor(port_id=port_id, why="unrecognised interface name")

    slot = int(match["slot"])
    port = int(match["port"])
    lane = int(match["lane"]) if match["lane"] else 0

    if slot != 1:
        raise InvalidLagAnchor(port_id=port_id, why="slot must be 1")
    if not 1 <= port <= MAX_PORT:
        raise InvalidLagAnchor(port_id=port_id, why=f"port must be 1-{MAX_PORT}")
    if match["lane"] and not 1 <= lane <= MAX_LANE:
        raise InvalidLagAnchor(port_id=port_id, why=f"lane must be 1-{MAX_LANE}")

    digit = lane + (SECOND_SWITCH_OFFSET if second_switch else 0)
    return f"Po{1000 + port * 10 + digit}"


def for_profile(profile: dict) -> str | None:
    """Return the LAG name for a binding profile, or None if it is not bonded.

    update_port_precommit stores the name under ``lag``. Ports bound before that
    have none, so derive it from the first local_link_information entry.
    """
    group = profile.get("local_group_information")
    if not group:
        return None
    if group.get("lag"):
        return group["lag"]

    links = profile.get("local_link_information") or []
    if not links:
        raise InvalidLagAnchor(port_id="", why="no local_link_information")
    return lag_name(links[0].get("port_id", ""))
