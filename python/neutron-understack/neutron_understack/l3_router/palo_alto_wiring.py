"""Neutron and Ironic wiring for the Palo Alto router flavor.

A router's gateway and interfaces reach its adopted Ironic node through one
stack: a parent port on the shared anchor network, VIF-attached to the node,
with a trunk whose VLAN subports are the router's own ports. This module holds
that wiring logic without any Neutron callback subscriptions.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

from neutron_lib import exceptions as n_exc
from neutron_lib.api.definitions import portbindings
from neutron_lib.services.trunk import constants as trunk_consts

from neutron_understack import utils

# Single shared sentinel network owned by the router flavor code.
ANCHOR_NETWORK_NAME = "palo_alto_router_anchor_network"

# Deterministic per-router names. Deriving the parent port and trunk names from
# the router id lets the gateway teardown find them by name without depending on
# catching a specific delete event with the gateway port still visible.
ANCHOR_PARENT_PORT_NAME_PREFIX = "palo-alto-router-anchor"
TRUNK_NAME_PREFIX = "palo-alto-router-trunk"

# Temporary fixed trunk subport tag. This keeps the subport segmentation_id in
# the existing allowed/gap VLAN validation path. Replace with a configured or
# allocated model once the trunk-tag semantics are revisited.
GATEWAY_SUBPORT_VLAN = 200
INTERFACE_SUBPORT_VLAN_START = GATEWAY_SUBPORT_VLAN + 1

# Which kind of router port a trunk subport carries; used in log messages.
PortLabel = Literal["gateway", "interface"]


@dataclass(frozen=True)
class AttachmentSnapshot:
    """Router wiring that existed before an interface attach request.

    Rollback compares current state against this, so it removes only what the
    request added and leaves pre-existing parent, trunk and VIF in place.
    """

    router_id: str
    port_id: str
    parent_id: str | None
    trunk_id: str | None
    subport_present: bool
    parent_vif_attached: bool


# Conflict -> HTTP 409: every allowed VLAN on the router's trunk is in use.
class NoPaloAltoSubportVlanAvailable(n_exc.Conflict):
    message = (
        "No Palo Alto trunk subport VLAN is available for router %(router_id)s "
        "on trunk %(trunk_id)s. Allowed ranges: %(network_segment_ranges)s."
    )


# BadRequest -> HTTP 400: the router has no adopted node to wire.
class PaloAltoNodeNotAdopted(n_exc.BadRequest):
    message = (
        "Palo Alto router %(router_id)s has no adopted Ironic node to attach "
        "its anchor parent port to."
    )


# BadRequest -> HTTP 400: the node's baremetal port is missing enrollment data.
class PaloAltoParentNotAnnotated(n_exc.BadRequest):
    message = (
        "Palo Alto router %(router_id)s parent port %(port_id)s was not "
        "annotated by Ironic (missing %(missing)s); check the node's baremetal "
        "port has physical_network."
    )


def _parent_port_name(router_id: str) -> str:
    """Deterministic name for the router's anchor-network parent port."""
    return f"{ANCHOR_PARENT_PORT_NAME_PREFIX}-{router_id}"


def _trunk_name(router_id: str) -> str:
    """Deterministic name for the router's trunk."""
    return f"{TRUNK_NAME_PREFIX}-{router_id}"


def _has_subport(trunk: dict, port_id: str) -> bool:
    """Return True if the port is already a subport on the trunk."""
    return any(sp["port_id"] == port_id for sp in trunk.get("sub_ports", []))


def _used_subport_vlans(trunk: dict) -> set[int]:
    """Return VLAN segmentation IDs already used on a router trunk."""
    return {
        sp["segmentation_id"]
        for sp in trunk.get("sub_ports", [])
        if sp.get("segmentation_type") == trunk_consts.SEGMENTATION_TYPE_VLAN
        and sp.get("segmentation_id") is not None
    }


def _first_free_vlan(
    ranges: list[tuple[int, int]], used: set[int], start: int
) -> int | None:
    """Return the lowest VLAN >= start that is in ranges and not used, or None."""
    for low, high in sorted(ranges):
        for vlan in range(max(low, start), high + 1):
            if vlan not in used:
                return vlan
    return None


@contextmanager
def _device_id_cleared(port: dict) -> Generator[None, None, None]:
    """Clear the port's device_id for the block, then restore device_id + owner."""
    # Note: The trunk subport validator rejects a port that has device_id set
    # (rules.py check_not_in_use). Router-owned ports have
    # device_id=router_id, so clear it for the add and restore it
    # afterwards so the router keeps its port association.
    original_device_id = port["device_id"]
    original_device_owner = port["device_owner"]
    utils.clear_device_id_for_port(port["id"])
    try:
        yield
    finally:
        utils.set_device_id_and_owner_for_port(
            port["id"], original_device_id, original_device_owner
        )


def _missing_binding_fields(port: dict) -> list[str]:
    """Return the binding fields Ironic should have set on the port but did not."""
    profile = port.get(portbindings.PROFILE) or {}
    return [
        name
        for name, value in (
            (portbindings.HOST_ID, port.get(portbindings.HOST_ID)),
            ("physical_network", profile.get("physical_network")),
            ("local_link_information", profile.get("local_link_information")),
        )
        if not value
    ]
