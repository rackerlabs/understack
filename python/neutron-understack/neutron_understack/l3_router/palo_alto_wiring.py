"""Neutron and Ironic wiring for the Palo Alto router flavor.

A router's gateway and interfaces reach its adopted Ironic node through one
stack: a parent port on the shared anchor network, VIF-attached to the node,
with a trunk whose VLAN subports are the router's own ports. A node whose ports
carry roles gets one stack per side instead: the gateway on the outside NIC and
the subnets on the inside NIC. This module holds that wiring logic without any
Neutron callback subscriptions.
"""

import logging
from collections.abc import Callable
from collections.abc import Generator
from contextlib import contextmanager
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Literal

from neutron.extensions import tagging
from neutron_lib import constants as const
from neutron_lib import context as n_context
from neutron_lib import exceptions as n_exc
from neutron_lib.api.definitions import portbindings
from neutron_lib.plugins import directory
from neutron_lib.services.trunk import constants as trunk_consts
from openstack.baremetal.v1.node import Node as BaremetalNode

from neutron_understack import utils
from neutron_understack.ironic import IronicClient
from neutron_understack.ironic import is_ha_primary
from neutron_understack.ironic import uses_port_roles

LOG = logging.getLogger(__name__)

# Single shared sentinel network owned by the router flavor code.
ANCHOR_NETWORK_NAME = "palo_alto_router_anchor_network"

# Deterministic per-router names. Deriving the parent port and trunk names from
# the router id lets the gateway teardown find them by name without depending on
# catching a specific delete event with the gateway port still visible.
ANCHOR_PARENT_PORT_NAME_PREFIX = "palo-alto-router-anchor"
TRUNK_NAME_PREFIX = "palo-alto-router-trunk"
# The HA secondary's stand-in for a router port: a subport can be on one trunk.
MIRROR_PORT_NAME_PREFIX = "palo-alto-router-mirror"

# Temporary fixed trunk subport tag. This keeps the subport segmentation_id in
# the existing allowed/gap VLAN validation path. Replace with a configured or
# allocated model once the trunk-tag semantics are revisited.
GATEWAY_SUBPORT_VLAN = 200
INTERFACE_SUBPORT_VLAN_START = GATEWAY_SUBPORT_VLAN + 1

# Which kind of router port a trunk subport carries; used in log messages.
PortLabel = Literal["gateway", "interface"]

# On a node whose ports carry roles, each side of the router has its own NIC,
# parent port and trunk: the gateway goes outside, the subnets inside. The
# side's name is also the tag on its parent port.
Side = Literal["outside", "inside"]
LABEL_SIDES: dict[PortLabel, Side] = {"gateway": "outside", "interface": "inside"}

# Which unit of an HA pair a stack is wired to. The secondary's stack mirrors
# the primary's on the same VLAN tags, so traffic reaches whichever is active.
Member = Literal["primary", "secondary"]


@dataclass(frozen=True)
class AttachmentSnapshot:
    """Router wiring that existed before a gateway or interface attach request.

    Rollback compares current state against this, so it removes only what the
    request added and leaves pre-existing parent, trunk and VIF in place.
    """

    router_id: str
    port_id: str
    label: PortLabel
    parent_id: str | None
    trunk_id: str | None
    subport_present: bool
    parent_vif_attached: bool
    # The stack the attach used; None on a node without port roles.
    side: Side | None = None
    # On an HA pair: this snapshot's unit, the mirror port that already existed
    # (secondary only), and the secondary's own snapshot (primary only).
    member: Member = "primary"
    mirror_id: str | None = None
    secondary: "AttachmentSnapshot | None" = None


@dataclass(frozen=True)
class AttachmentStack:
    """A router's VIF-bound anchor parent port and the trunk built on it."""

    parent: dict
    trunk: dict


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


# BadRequest -> HTTP 400: no NIC on the node can carry the parent port's VIF.
class PaloAltoNodeHasNoUsablePort(n_exc.BadRequest):
    message = (
        "Ironic node %(node_id)s for Palo Alto router %(router_id)s has no "
        "baremetal port with both physical_network and local_link_connection; "
        "check the node's port enrollment."
    )


# BadRequest -> HTTP 400: Ironic did not put a side's parent VIF on that side's NIC.
class PaloAltoParentNotOnSideNic(n_exc.BadRequest):
    message = (
        "Palo Alto router %(router_id)s %(side)s parent port %(port_id)s was "
        "attached to %(nic)s, not to the node's %(side)s NIC; check the node's "
        "port categories and Ironic's CUSTOM_NETDEV_ROLE_ATTACH rule."
    )


# BadRequest -> HTTP 400: a node with port roles has no usable NIC for this side.
class PaloAltoNodeHasNoSideNic(n_exc.BadRequest):
    message = (
        "Ironic node %(node_id)s for Palo Alto router %(router_id)s has no "
        "baremetal port with category %(side)s, physical_network and "
        "local_link_connection; check the node's port enrollment."
    )


# Conflict -> HTTP 409: the router's HA secondary is not claimed (being replaced).
class PaloAltoHaSecondaryMissing(n_exc.Conflict):
    message = (
        "Palo Alto router %(router_id)s runs on HA primary %(node_id)s, but no "
        "secondary is claimed for it; replace the secondary before wiring."
    )


def _stack_name(name: str, side: Side | None, member: Member) -> str:
    """Add the side, and -secondary for the HA secondary's stack."""
    if side:
        name = f"{name}-{side}"
    return f"{name}-secondary" if member == "secondary" else name


def _parent_port_name(
    router_id: str, side: Side | None = None, member: Member = "primary"
) -> str:
    """Deterministic name for the router's (or a side's) anchor parent port."""
    return _stack_name(f"{ANCHOR_PARENT_PORT_NAME_PREFIX}-{router_id}", side, member)


def _trunk_name(
    router_id: str, side: Side | None = None, member: Member = "primary"
) -> str:
    """Deterministic name for the router's (or a side's) trunk."""
    return _stack_name(f"{TRUNK_NAME_PREFIX}-{router_id}", side, member)


def _mirror_port_name(router_id: str, port_id: str) -> str:
    """Deterministic name for the secondary's stand-in for a router port."""
    return f"{MIRROR_PORT_NAME_PREFIX}-{router_id}-{port_id}"


def _find_subport(trunk: dict, port_id: str) -> dict | None:
    """Return the port's subport entry on the trunk, or None."""
    return next(
        (sp for sp in trunk.get("sub_ports", []) if sp["port_id"] == port_id), None
    )


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


def _is_bindable_port(port) -> bool:
    """Return True if Ironic can annotate a parent VIF attached to this port."""
    return bool(port.physical_network) and bool(port.local_link_connection)


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


class PaloAltoWiring:
    """Build and tear down a Palo Alto router's parent port, VIF and trunk.

    Lookups are methods, not properties, so inspecting this object never
    contacts Neutron or Ironic.
    """

    def __init__(self, ironic: Callable[[], IronicClient]):
        # A getter rather than a client: the client is still created lazily,
        # and the provider and the wiring share one instance.
        self._get_ironic = ironic

    def _ironic(self) -> IronicClient:
        return self._get_ironic()

    def _trunk_plugin(self):
        return utils.fetch_trunk_plugin()

    def _core_plugin(self):
        return directory.get_plugin()

    def _admin_context(self):
        return n_context.get_admin_context()

    def _tag_plugin(self):
        return directory.get_plugin(tagging.TAG_PLUGIN_TYPE)

    def _node_for_router(self, router_id: str) -> BaremetalNode | None:
        """Return the Ironic node adopted for the router, or None."""
        return self._ironic().node_by_instance_uuid(router_id)

    def _node_for_member(self, router_id: str, member: Member) -> BaremetalNode | None:
        """Return the router's primary node, or its HA secondary, or None."""
        if member == "primary":
            return self._node_for_router(router_id)
        secondaries = self._ironic().secondaries_for_router(router_id)
        return secondaries[0] if secondaries else None

    def _members(self, router_id: str) -> dict[Member, BaremetalNode]:
        """Return the nodes to wire: the primary, and its HA secondary if any.

        Refuses an HA primary whose secondary is not claimed, so a router is
        never wired on half a pair.
        """
        node = self._node_for_router(router_id)
        if node is None:
            raise PaloAltoNodeNotAdopted(router_id=router_id)
        secondaries = self._ironic().secondaries_for_router(router_id)
        if secondaries:
            return {"primary": node, "secondary": secondaries[0]}
        if is_ha_primary(node):
            raise PaloAltoHaSecondaryMissing(router_id=router_id, node_id=node.id)
        return {"primary": node}

    def _attach_side(self, router_id: str, label: PortLabel) -> Side | None:
        """Return the side a new attachment uses, or None without port roles."""
        node = self._node_for_router(router_id)
        if node is None or not uses_port_roles(node):
            return None
        return LABEL_SIDES[label]

    def _existing_side(self, router_id: str, label: PortLabel) -> Side | None:
        """Return the side whose stack exists for this label, or None.

        Decided from Neutron alone, so teardown still finds the stack after the
        node has been released.
        """
        side = LABEL_SIDES[label]
        for member in ("primary", "secondary"):
            if self._trunk_for_router(router_id, side, member) is not None:
                return side
            if self._parent_port_for_router(router_id, side, member) is not None:
                return side
        return None

    def ensure_anchor_network(self) -> dict:
        """Create the shared sentinel anchor network if it does not exist."""
        core_plugin = self._core_plugin()
        admin_context = self._admin_context()
        existing = core_plugin.get_networks(
            admin_context, filters={"name": [ANCHOR_NETWORK_NAME]}
        )
        if existing:
            LOG.debug(
                "Reusing existing anchor network %s (id=%s)",
                ANCHOR_NETWORK_NAME,
                existing[0]["id"],
            )
            return existing[0]
        LOG.info("Creating shared anchor network %s", ANCHOR_NETWORK_NAME)
        # Calling the core plugin directly (not via the REST API) skips the
        # API layer that fills in extension-attribute defaults, so we must
        # supply them ourselves. project_id (ownership) and router:external
        # (read by the auto_allocate NETWORK-create callback) are required;
        # without router:external the create fails with KeyError 'router:external'.
        return core_plugin.create_network(
            admin_context,
            {
                "network": {
                    "name": ANCHOR_NETWORK_NAME,
                    "admin_state_up": True,
                    "shared": False,
                    "router:external": False,
                    "project_id": admin_context.project_id or "",
                }
            },
        )

    def gateway_port_for_router(self, router_id: str) -> dict | None:
        """Return the router's Neutron external-gateway port, or None.

        The gateway port is owned by the router (``device_id == router_id``) with
        ``device_owner == network:router_gateway``.
        """
        core_plugin = self._core_plugin()
        admin_context = self._admin_context()
        ports = core_plugin.get_ports(
            admin_context,
            filters={
                "device_id": [router_id],
                "device_owner": [const.DEVICE_OWNER_ROUTER_GW],
            },
        )
        if not ports:
            LOG.debug("No gateway port found for Palo Alto router %s", router_id)
            return None
        if len(ports) > 1:
            LOG.warning(
                "Expected one gateway port for Palo Alto router %s, found %d; using %s",
                router_id,
                len(ports),
                ports[0]["id"],
            )
        return ports[0]

    def _parent_port_for_router(
        self, router_id: str, side: Side | None = None, member: Member = "primary"
    ) -> dict | None:
        """Return the router's existing anchor-network parent port, or None."""
        core_plugin = self._core_plugin()
        admin_context = self._admin_context()
        anchor_network = self.ensure_anchor_network()
        ports = core_plugin.get_ports(
            admin_context,
            filters={
                "name": [_parent_port_name(router_id, side, member)],
                "network_id": [anchor_network["id"]],
            },
        )
        return ports[0] if ports else None

    def _create_parent_port(
        self, router_id: str, side: Side | None = None, member: Member = "primary"
    ) -> dict:
        """Create the router's parent port on the anchor network.

        vnic_type=baremetal so Ironic can VIF-attach it to the adopted node.
        """
        core_plugin = self._core_plugin()
        admin_context = self._admin_context()
        anchor_network = self.ensure_anchor_network()
        port_name = _parent_port_name(router_id, side, member)
        LOG.info(
            "Creating Palo Alto anchor parent port %s for router %s",
            port_name,
            router_id,
        )
        port = core_plugin.create_port(
            admin_context,
            {
                "port": {
                    "name": port_name,
                    "network_id": anchor_network["id"],
                    "admin_state_up": True,
                    "device_owner": "",
                    "device_id": router_id,
                    "mac_address": "",
                    "fixed_ips": [],
                    "project_id": admin_context.project_id or "",
                    portbindings.VNIC_TYPE: portbindings.VNIC_BAREMETAL,
                }
            },
        )
        return port

    def _ensure_parent_port(
        self, router_id: str, side: Side | None = None, member: Member = "primary"
    ) -> dict:
        """Find-or-create the router's anchor-network parent port (idempotent)."""
        port = self._parent_port_for_router(router_id, side, member)
        if port is not None:
            LOG.debug(
                "Reusing Palo Alto anchor parent port %s for router %s",
                port["id"],
                router_id,
            )
        else:
            port = self._create_parent_port(router_id, side, member)
        if side is not None and port.get("tags") != [side]:
            # Ironic's TBN rule matches this tag (vif.tags) to the NIC's
            # category, so a reused port that lost it is tagged again.
            self._tag_plugin().update_tags(
                self._admin_context(), "ports", port["id"], {"tags": [side]}
            )
        return port

    def _fresh_port(self, port_id: str) -> dict:
        """Re-read a port so callers see its current binding profile."""
        core_plugin = self._core_plugin()
        admin_context = self._admin_context()
        return core_plugin.get_port(admin_context, port_id)

    def _vif_landed_after_error(
        self, router_id: str, node, parent_port_id: str
    ) -> bool:
        """Return True if an errored attach actually attached the VIF.

        Ironic VIF attach can time out waiting for the conductor/RPC reply even
        after the conductor has applied the binding.
        """
        try:
            vif_ids = self._ironic().node_vif_ids(node)
        except Exception:
            LOG.debug(
                "Could not re-check VIF attachments for Palo Alto router %s "
                "after an attach error",
                router_id,
                exc_info=True,
            )
            return False
        return parent_port_id in vif_ids

    def _verify_parent_on_side_nic(
        self, router_id: str, node, parent_port_id: str, side: Side
    ) -> None:
        """Fail if Ironic did not put the side's parent VIF on that side's NIC.

        Ironic's TBN rule should place it, but if TBN is off or its rules
        changed, the VIF can land on another NIC or none.
        """
        nic = self._ironic().port_for_vif(node, parent_port_id)
        if nic is None or nic.category != side:
            raise PaloAltoParentNotOnSideNic(
                router_id=router_id,
                side=side,
                port_id=parent_port_id,
                nic=f"NIC {nic.name}" if nic is not None else "no NIC",
            )

    def _ensure_parent_vif_attached(
        self,
        router_id: str,
        parent_port: dict,
        side: Side | None = None,
        member: Member = "primary",
    ) -> dict:
        """VIF-attach the parent port to the router's node (idempotent).

        Attaching a single VIF; Ironic binds it to a free baremetal port on the
        node and annotates the Neutron port with local_link_information +
        physical_network and host_id . With a side, Ironic must pick that
        side's NIC.

        Returns a fresh copy of the parent port reflecting the new binding.
        """
        node = self._node_for_member(router_id, member)
        if node is None:
            raise PaloAltoNodeNotAdopted(router_id=router_id)

        parent_port_id = parent_port["id"]
        if parent_port_id in self._ironic().node_vif_ids(node):
            LOG.debug(
                "Parent port %s already VIF-attached to node %s",
                parent_port_id,
                node.id,
            )
        else:
            try:
                self._ironic().attach_vif_to_node(node, parent_port_id)
            except Exception:
                if not self._vif_landed_after_error(router_id, node, parent_port_id):
                    raise
                LOG.warning(
                    "Ironic VIF attach for Palo Alto router %s parent port %s "
                    "on node %s raised, but the VIF is attached; continuing",
                    router_id,
                    parent_port_id,
                    node.id,
                    exc_info=True,
                )

        if side is not None:
            self._verify_parent_on_side_nic(router_id, node, parent_port_id, side)
        fresh = self._fresh_port(parent_port_id)
        self._verify_parent_annotated(router_id, fresh)
        return fresh

    def _verify_parent_annotated(self, router_id: str, parent_port: dict) -> None:
        """Fail fast if Ironic did not annotate the parent port.

        The trunk + undersync need host_id, physical_network and
        local_link_information on the binding profile. If they are missing the
        node's baremetal port most likely has no physical_network (enroll side);
        surface a clear error here.
        """
        missing = _missing_binding_fields(parent_port)
        if missing:
            raise PaloAltoParentNotAnnotated(
                router_id=router_id,
                port_id=parent_port["id"],
                missing=", ".join(missing),
            )

    def _trunk_for_router(
        self, router_id: str, side: Side | None = None, member: Member = "primary"
    ) -> dict | None:
        """Return the router's existing trunk (by deterministic name), or None."""
        admin_context = self._admin_context()
        trunks = self._trunk_plugin().get_trunks(
            admin_context, filters={"name": [_trunk_name(router_id, side, member)]}
        )
        return trunks[0] if trunks else None

    def _create_trunk(
        self,
        router_id: str,
        parent_port: dict,
        side: Side | None = None,
        member: Member = "primary",
    ) -> dict:
        """Create the router's trunk with the parent port as its trunk parent."""
        admin_context = self._admin_context()
        trunk_name = _trunk_name(router_id, side, member)
        LOG.info(
            "Creating Palo Alto trunk %s on parent port %s for router %s",
            trunk_name,
            parent_port["id"],
            router_id,
        )
        return self._trunk_plugin().create_trunk(
            admin_context,
            {
                "trunk": {
                    "name": trunk_name,
                    "port_id": parent_port["id"],
                    "admin_state_up": True,
                    "project_id": admin_context.project_id or "",
                    "sub_ports": [],
                }
            },
        )

    def _ensure_trunk(
        self,
        router_id: str,
        parent_port: dict,
        side: Side | None = None,
        member: Member = "primary",
    ) -> dict:
        """Find-or-create the router's trunk (idempotent)."""
        existing = self._trunk_for_router(router_id, side, member)
        if existing is not None:
            LOG.debug(
                "Reusing Palo Alto trunk %s for router %s",
                existing["id"],
                router_id,
            )
            return existing
        return self._create_trunk(router_id, parent_port, side, member)

    def check_can_attach(self, router_id: str) -> None:
        """Raise if the router's nodes cannot be wired for a gateway. Read-only.

        On a node with port roles, the NIC must be the outside one.
        """
        for node in self._members(router_id).values():
            self._check_node_can_attach(router_id, node)

    def _check_node_can_attach(self, router_id: str, node: BaremetalNode) -> None:
        """Raise unless one of the node's NICs can carry the gateway."""
        ports = self._ironic().node_ports(node)
        if not uses_port_roles(node):
            if not any(_is_bindable_port(port) for port in ports):
                raise PaloAltoNodeHasNoUsablePort(router_id=router_id, node_id=node.id)
            return
        side = LABEL_SIDES["gateway"]
        if not any(_is_bindable_port(port) and port.category == side for port in ports):
            raise PaloAltoNodeHasNoSideNic(
                router_id=router_id, node_id=node.id, side=side
            )

    def ensure_stack(
        self, router_id: str, side: Side | None = None, member: Member = "primary"
    ) -> AttachmentStack:
        """Find or create the router's parent port, VIF attachment and trunk.

        Builds them in this order so the parent is VIF-bound before any subport
        is added: the trunk driver only programs the switchport once the parent
        is bound. With a side, builds that side's stack.
        """
        parent = self._ensure_parent_port(router_id, side, member)
        parent = self._ensure_parent_vif_attached(router_id, parent, side, member)
        trunk = self._ensure_trunk(router_id, parent, side, member)
        return AttachmentStack(parent=parent, trunk=trunk)

    def _next_available_subport_vlan(
        self, router_id: str, trunks: list[dict], start_vlan: int
    ) -> int:
        """Pick the first allowed Palo Alto subport VLAN from start, free on all."""
        ranges = utils.allowed_tenant_vlan_id_ranges()
        used = set().union(*(_used_subport_vlans(trunk) for trunk in trunks))
        vlan = _first_free_vlan(ranges, used, start_vlan)
        if vlan is None:
            raise NoPaloAltoSubportVlanAvailable(
                router_id=router_id,
                trunk_id=", ".join(trunk["id"] for trunk in trunks),
                network_segment_ranges=utils.printable_ranges(sorted(ranges)),
            )
        return vlan

    def _mirror_port(self, router_id: str, port_id: str) -> dict | None:
        """Return the secondary's stand-in for a router port, or None."""
        ports = self._core_plugin().get_ports(
            self._admin_context(),
            filters={"name": [_mirror_port_name(router_id, port_id)]},
        )
        return ports[0] if ports else None

    def _mirror_port_id(self, router_id: str, port_id: str) -> str | None:
        """Return the id of the secondary's stand-in for a router port, or None."""
        mirror = self._mirror_port(router_id, port_id)
        return mirror["id"] if mirror else None

    def _delete_mirror_port(self, mirror_id: str) -> None:
        LOG.info("Deleting Palo Alto mirror port %s", mirror_id)
        self._core_plugin().delete_port(self._admin_context(), mirror_id)

    def _ensure_mirror_port(self, router_id: str, router_port: dict) -> dict:
        """Find or create the secondary's stand-in for a router port.

        Same network, so the same fabric VLAN reaches the secondary. No IP: the
        router port keeps it, and PAN-OS moves it to whichever unit is active,
        so the mirror is allowed to use it.
        """
        existing = self._mirror_port(router_id, router_port["id"])
        if existing is not None:
            return existing
        core_plugin = self._core_plugin()
        admin_context = self._admin_context()
        port = {
            "name": _mirror_port_name(router_id, router_port["id"]),
            "network_id": router_port["network_id"],
            "admin_state_up": True,
            "device_owner": "",
            "device_id": "",
            "mac_address": "",
            "fixed_ips": [],
            "project_id": admin_context.project_id or "",
        }
        network = core_plugin.get_network(admin_context, router_port["network_id"])
        # Neutron refuses address pairs where port security is off; nothing is
        # filtered there anyway.
        if network.get("port_security_enabled", True):
            port["allowed_address_pairs"] = [
                {"ip_address": fixed_ip["ip_address"]}
                for fixed_ip in router_port.get("fixed_ips", [])
            ]
        LOG.info(
            "Creating Palo Alto mirror port %s for router %s port %s",
            port["name"],
            router_id,
            router_port["id"],
        )
        return core_plugin.create_port(admin_context, {"port": port})

    def _add_router_port_subport(
        self,
        router_id: str,
        trunk: dict,
        port: dict,
        label: PortLabel,
        pick_vlan: Callable[[], int],
    ) -> int:
        """Add a router-owned port to the trunk as a VLAN subport; return its VLAN.

        Adding the subport fires the understack trunk driver (SUBPORTS events),
        which allocates the fabric segment, binds it, and calls undersync to
        program the switch. No-ops if the port is already a subport.

        A port on a fabric_vlan network must be tagged with that fabric_vlan
        (the trunk driver rejects any other tag), so it takes precedence over
        pick_vlan. pick_vlan is called only when the port is actually added and
        has no fabric_vlan, so an exhausted VLAN pool cannot fail an
        already-attached port.
        """
        port_id = port["id"]
        existing = _find_subport(trunk, port_id)
        if existing is not None:
            LOG.debug(
                "Palo Alto %s port %s already a subport on trunk %s",
                label,
                port_id,
                trunk["id"],
            )
            return existing.get("segmentation_id")

        fabric_vlan = utils.network_fabric_vlan(port["network_id"])
        segmentation_id = fabric_vlan if fabric_vlan is not None else pick_vlan()
        admin_context = self._admin_context()
        LOG.info(
            "Adding Palo Alto %s port %s to trunk %s as VLAN %s subport for router %s",
            label,
            port_id,
            trunk["id"],
            segmentation_id,
            router_id,
        )
        # A router port has the router as device_id; a mirror port has none.
        with _device_id_cleared(port) if port["device_id"] else nullcontext():
            self._trunk_plugin().add_subports(
                admin_context,
                trunk["id"],
                {
                    "sub_ports": [
                        {
                            "port_id": port_id,
                            "segmentation_type": trunk_consts.SEGMENTATION_TYPE_VLAN,
                            "segmentation_id": segmentation_id,
                        }
                    ]
                },
            )
        return segmentation_id

    def add_gateway_subport(
        self, router_id: str, trunk: dict, gateway_port: dict
    ) -> int:
        """Add the gateway port to the trunk as a VLAN subport (idempotent)."""
        return self._add_router_port_subport(
            router_id, trunk, gateway_port, "gateway", lambda: GATEWAY_SUBPORT_VLAN
        )

    def add_interface_subport(
        self, router_id: str, trunk: dict, interface_port: dict, *other_trunks: dict
    ) -> int:
        """Add a router-interface port to the trunk as a VLAN subport.

        The VLAN is free on the other trunks too, so an HA pair shares it.
        """
        return self._add_router_port_subport(
            router_id,
            trunk,
            interface_port,
            "interface",
            lambda: self._next_available_subport_vlan(
                router_id, [trunk, *other_trunks], INTERFACE_SUBPORT_VLAN_START
            ),
        )

    def attach_port(
        self, router_id: str, port: dict, label: PortLabel
    ) -> AttachmentStack:
        """Build the router's stack (the label's side's, if any), add the subport.

        On an HA pair the secondary gets its own stack too, and a mirror of the
        port on the same VLAN. The primary is wired first.
        """
        side = self._attach_side(router_id, label)
        stack, *secondary_stacks = (
            self.ensure_stack(router_id, side, member)
            for member in self._members(router_id)
        )
        if label == "gateway":
            vlan = self.add_gateway_subport(router_id, stack.trunk, port)
        else:
            vlan = self.add_interface_subport(
                router_id, stack.trunk, port, *(s.trunk for s in secondary_stacks)
            )
        for secondary_stack in secondary_stacks:
            mirror = self._ensure_mirror_port(router_id, port)
            self._add_router_port_subport(
                router_id, secondary_stack.trunk, mirror, label, lambda: vlan
            )
        LOG.info(
            "Attached Palo Alto router %s %s port %s via parent %s trunk %s%s",
            router_id,
            label,
            port["id"],
            stack.parent["id"],
            stack.trunk["id"],
            " and its HA secondary" if secondary_stacks else "",
        )
        return stack

    def _remove_router_port_subport(
        self, trunk: dict, port_id: str, label: PortLabel
    ) -> dict:
        """Remove a router-owned port from the trunk (idempotent).

        Fires the trunk driver's SUBPORTS delete events, which release the
        fabric segment and update the switchport. No-ops if it is not a subport.
        """
        if _find_subport(trunk, port_id) is None:
            LOG.debug(
                "Palo Alto %s port %s is not a subport on trunk %s; skip removal",
                label,
                port_id,
                trunk["id"],
            )
            return trunk
        admin_context = self._admin_context()
        LOG.info(
            "Removing Palo Alto %s subport %s from trunk %s",
            label,
            port_id,
            trunk["id"],
        )
        return self._trunk_plugin().remove_subports(
            admin_context,
            trunk["id"],
            {"sub_ports": [{"port_id": port_id}]},
        )

    def _detach_parent_vif(
        self, router_id: str, parent: dict, member: Member = "primary"
    ) -> None:
        """Detach the parent's VIF from its node, if there is one.

        The node is the port's binding host, which still works after the node
        is released; a port Ironic never annotated falls back to the unit's
        claimed node.
        """
        node = parent.get(portbindings.HOST_ID) or self._node_for_member(
            router_id, member
        )
        if not node:
            LOG.debug(
                "Palo Alto router %s parent %s has no node to detach from",
                router_id,
                parent["id"],
            )
            return
        self._ironic().detach_vif_from_node(node, parent["id"])

    def _detach_and_delete_parent(
        self, router_id: str, parent_id: str, member: Member = "primary"
    ) -> None:
        """Detach the parent VIF from the node and delete the parent port."""
        self._detach_parent_vif(router_id, self._fresh_port(parent_id), member)
        core_plugin = self._core_plugin()
        admin_context = self._admin_context()
        LOG.info("Deleting Palo Alto anchor parent port %s", parent_id)
        core_plugin.delete_port(admin_context, parent_id)

    def _delete_parent_stack_if_unused(
        self, router_id: str, trunk: dict, member: Member = "primary"
    ) -> None:
        """Delete the trunk + parent port only if no subports remain.

        Re-reads the trunk so a subport removed just before this is reflected. If
        other subports are still present (e.g. tenant subnets), leave the trunk
        and parent for them to share.
        """
        admin_context = self._admin_context()
        fresh = self._trunk_plugin().get_trunk(admin_context, trunk["id"])
        if fresh.get("sub_ports"):
            LOG.debug(
                "Trunk %s still has subports; leaving parent stack for router %s",
                trunk["id"],
                router_id,
            )
            return
        parent_id = fresh["port_id"]
        LOG.info(
            "Deleting Palo Alto trunk %s (no subports left) for router %s",
            trunk["id"],
            router_id,
        )
        self._trunk_plugin().delete_trunk(admin_context, trunk["id"])
        self._detach_and_delete_parent(router_id, parent_id, member)

    def cleanup_attachment(
        self,
        router_id: str,
        port_id: str,
        label: PortLabel,
    ) -> None:
        """Reverse of the add: remove subport, then tear down the parent stack.

        Handles a partially-built attach too: if a prior add failed after the
        parent port was created/VIF-attached but before the trunk existed, there
        is no trunk to key off, so find and tear down the orphan parent directly.
        On a node with port roles, only the label's side's stack is touched.
        On an HA pair the secondary's mirror and stack go first.
        """
        side = self._existing_side(router_id, label)
        mirror_id = self._mirror_port_id(router_id, port_id)
        self._cleanup_stack(router_id, mirror_id, label, side, "secondary")
        if mirror_id is not None:
            self._delete_mirror_port(mirror_id)
        self._cleanup_stack(router_id, port_id, label, side, "primary")

    def _cleanup_stack(
        self,
        router_id: str,
        port_id: str | None,
        label: PortLabel,
        side: Side | None,
        member: Member,
    ) -> None:
        """Remove the port from one unit's trunk, then that stack if unused."""
        trunk = self._trunk_for_router(router_id, side, member)
        if trunk is None:
            parent = self._parent_port_for_router(router_id, side, member)
            if parent is not None:
                LOG.info(
                    "No trunk for Palo Alto router %s; deleting orphan parent %s",
                    router_id,
                    parent["id"],
                )
                self._detach_and_delete_parent(router_id, parent["id"], member)
            else:
                LOG.debug(
                    "No trunk or parent for Palo Alto router %s; nothing to clean up",
                    router_id,
                )
            return
        if port_id is not None:
            self._remove_router_port_subport(trunk, port_id, label)
        self._delete_parent_stack_if_unused(router_id, trunk, member)

    def snapshot_attachment(
        self, router_id: str, port_id: str, label: PortLabel
    ) -> AttachmentSnapshot:
        """Record which wiring already exists before attaching a router port."""
        side = self._attach_side(router_id, label)
        secondary = None
        if self._ironic().secondaries_for_router(router_id):
            secondary = self._snapshot_stack(
                router_id,
                port_id,
                label,
                side,
                "secondary",
                mirror_id=self._mirror_port_id(router_id, port_id),
            )
        return self._snapshot_stack(
            router_id, port_id, label, side, "primary", secondary=secondary
        )

    def _snapshot_stack(
        self,
        router_id: str,
        port_id: str,
        label: PortLabel,
        side: Side | None,
        member: Member,
        mirror_id: str | None = None,
        secondary: AttachmentSnapshot | None = None,
    ) -> AttachmentSnapshot:
        """Record one unit's wiring; on the secondary the subport is the mirror."""
        parent = self._parent_port_for_router(router_id, side, member)
        trunk = self._trunk_for_router(router_id, side, member)
        parent_vif_attached = False
        if parent is not None:
            node = self._node_for_member(router_id, member)
            if node is not None:
                parent_vif_attached = parent["id"] in self._ironic().node_vif_ids(node)
        subport_id = mirror_id if member == "secondary" else port_id
        return AttachmentSnapshot(
            router_id=router_id,
            port_id=port_id,
            label=label,
            parent_id=parent["id"] if parent else None,
            trunk_id=trunk["id"] if trunk else None,
            subport_present=bool(
                trunk and subport_id and _find_subport(trunk, subport_id)
            ),
            parent_vif_attached=parent_vif_attached,
            side=side,
            member=member,
            mirror_id=mirror_id,
            secondary=secondary,
        )

    def undo_attachment(self, snapshot: AttachmentSnapshot) -> None:
        """Return the router's wiring to the state recorded in the snapshot.

        Re-reads current state rather than replaying the calls that succeeded,
        because a remote call can apply its change and still raise.
        """
        if snapshot.secondary is not None:
            self._undo_stack(snapshot.secondary)
        self._undo_stack(snapshot)

    def _undo_stack(self, snapshot: AttachmentSnapshot) -> None:
        """Undo one unit's part of an attach; a mirror this attach made goes too."""
        router_id, side, member = snapshot.router_id, snapshot.side, snapshot.member
        subport_id, mirror_id = snapshot.port_id, None
        if member == "secondary":
            subport_id = mirror_id = self._mirror_port_id(router_id, snapshot.port_id)
        trunk = self._trunk_for_router(router_id, side, member)
        if trunk is not None and subport_id and not snapshot.subport_present:
            self._remove_router_port_subport(trunk, subport_id, snapshot.label)
        if mirror_id is not None and mirror_id != snapshot.mirror_id:
            self._delete_mirror_port(mirror_id)
        if trunk is not None:
            admin_context = self._admin_context()
            trunk = self._trunk_plugin().get_trunk(admin_context, trunk["id"])
            if trunk.get("sub_ports"):
                # Other interfaces still need the shared parent and VIF.
                return
            if trunk["id"] != snapshot.trunk_id:
                self._trunk_plugin().delete_trunk(admin_context, trunk["id"])

        parent = self._parent_port_for_router(router_id, side, member)
        if parent is not None:
            if parent["id"] != snapshot.parent_id:
                self._detach_and_delete_parent(router_id, parent["id"], member)
            elif not snapshot.parent_vif_attached:
                self._detach_parent_vif(router_id, parent, member)
