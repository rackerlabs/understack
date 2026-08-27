import json
import logging

from neutron.services.l3_router.service_providers import base
from neutron_lib import constants as const
from neutron_lib import context as n_context
from neutron_lib import exceptions as n_exc
from neutron_lib.api.definitions import portbindings
from neutron_lib.callbacks import events
from neutron_lib.callbacks import priority_group
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.plugins import constants as plugin_constants
from neutron_lib.plugins import directory

from neutron_understack import utils
from neutron_understack.ironic import IronicClient

LOG = logging.getLogger(__name__)

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


# Conflict -> HTTP 409: the request cannot be satisfied because the hardware
# pool is exhausted.
class NoNetdevNodeAvailable(n_exc.Conflict):
    message = (
        "No Ironic node with resource_class %(resource_class)s is available to "
        "realize router %(router_id)s."
    )


# BadRequest -> HTTP 400: the flavor/profile is misconfigured.
class PaloAltoFlavorMisconfigured(n_exc.BadRequest):
    message = (
        "Router %(router_id)s flavor %(flavor_id)s does not define a "
        "resource_class in its service profile metainfo."
    )


class NoPaloAltoSubportVlanAvailable(n_exc.Conflict):
    message = (
        "No Palo Alto trunk subport VLAN is available for router %(router_id)s "
        "on trunk %(trunk_id)s. Allowed ranges: %(network_segment_ranges)s."
    )


def _parse_metainfo(raw) -> dict:
    """Service-profile metainfo is stored as a JSON string."""
    if not raw:
        return {}
    # already a dict return as-is
    if isinstance(raw, dict):
        return raw
    # parse the string; malformed JSON
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


@registry.has_registry_receivers
class PaloAlto(base.L3ServiceProvider):
    """L3 service provider for the Palo Alto router flavor.

    A router of this flavor is realized on a netdev bare metal appliance. On
    create it adopts an available Ironic node (selected by the resource_class
    declared in the flavor's service profile metainfo), binds it to the owning
    project/router, and ensures the shared sentinel anchor network exists. On
    delete it returns the node to the available pool. Routers of this flavor are
    detected via their flavor's service profile driver.
    """

    ha_support = base.OPTIONAL

    def __init__(self, l3_plugin):
        super().__init__(l3_plugin)
        self._palo_alto_provider = f"{__name__}.{self.__class__.__name__}"
        # Gateway attach must run on AFTER_CREATE (the gateway port does not
        # exist earlier) and must be cancellable so a wiring failure returns a
        # real API error instead of a swallowed 200. @registry.receives cannot
        # set cancellable, so subscribe explicitly.
        registry.subscribe(
            self._process_gateway_create,
            resources.ROUTER_GATEWAY,
            events.AFTER_CREATE,
            cancellable=True,
        )
        # Remove runs on BEFORE_DELETE: the gateway port still exists there (it
        # is deleted only afterwards) so we can find it, and BEFORE_DELETE
        # re-raises callback errors. Note it runs inside a DB write transaction.
        registry.subscribe(
            self._process_gateway_delete,
            resources.ROUTER_GATEWAY,
            events.BEFORE_DELETE,
            cancellable=True,
        )
        registry.subscribe(
            self._process_router_interface_create,
            resources.ROUTER_INTERFACE,
            events.AFTER_CREATE,
            cancellable=True,
        )
        # Run before neutron.services.trunk.rules.enforce_port_deletion_rules
        # (PRIORITY_DEFAULT) so a Palo Alto router-interface port can be removed
        # from its trunk before Neutron checks whether the port is in use.
        registry.subscribe(
            self._process_router_interface_port_delete,
            resources.PORT,
            events.BEFORE_DELETE,
            priority=priority_group.PRIORITY_DEFAULT - 1000,
            cancellable=True,
        )
        LOG.info(
            "Palo Alto service provider initialized: driver=%r",
            self._palo_alto_provider,
        )

    @property
    def _flavor_plugin(self):
        try:
            return self._flavor_plugin_ref
        except AttributeError:
            self._flavor_plugin_ref = directory.get_plugin(plugin_constants.FLAVORS)
            return self._flavor_plugin_ref

    @property
    def _ironic(self) -> IronicClient:
        # Instantiated lazily so importing/loading this provider does not require
        # Ironic credentials in environments that never create such a router.
        try:
            return self._ironic_ref
        except AttributeError:
            self._ironic_ref = IronicClient()
            return self._ironic_ref

    def _is_palo_alto_provider(self, context, router):
        flavor_id = router.get("flavor_id")
        if flavor_id is None or flavor_id is const.ATTR_NOT_SPECIFIED:
            LOG.debug(
                "Palo Alto flavor check skipped: router=%s name=%s project=%s "
                "flavor=%s request_id=%s",
                router.get("id"),
                router.get("name"),
                router.get("project_id"),
                flavor_id,
                getattr(context, "request_id", None),
            )
            return False
        flavor = self._flavor_plugin.get_flavor(context, flavor_id)
        provider = self._flavor_plugin.get_flavor_next_provider(context, flavor["id"])[
            0
        ]
        actual_driver = str(provider["driver"])
        matched = actual_driver == self._palo_alto_provider
        LOG.debug(
            "Palo Alto flavor check: router=%s name=%s project=%s flavor=%s "
            "expected_driver=%s actual_driver=%s matched=%s request_id=%s",
            router.get("id"),
            router.get("name"),
            router.get("project_id"),
            flavor_id,
            self._palo_alto_provider,
            actual_driver,
            matched,
            getattr(context, "request_id", None),
        )
        return matched

    def _resource_class_for_router(self, context, router) -> str:
        """Read the target resource_class from the flavor's profile metainfo.

        This is a separate lookup from the driver match: the driver string
        selects *this code*, the metainfo resource_class selects *which
        hardware pool* to adopt from.
        """
        flavor = self._flavor_plugin.get_flavor(context, router["flavor_id"])
        for sp_id in flavor.get("service_profiles") or []:
            service_profile = self._flavor_plugin.get_service_profile(context, sp_id)
            resource_class = _parse_metainfo(service_profile.get("metainfo")).get(
                "resource_class"
            )
            if resource_class:
                return resource_class
        raise PaloAltoFlavorMisconfigured(
            router_id=router["id"], flavor_id=router["flavor_id"]
        )

    def _ensure_anchor_network(self):
        """Create the shared sentinel anchor network if it does not exist."""
        core_plugin = directory.get_plugin()
        admin_context = n_context.get_admin_context()
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
        # Not using API,coz _process_router_create runs as a callback inside the
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

    # --- gateway attachment: names + lookups (read-only) ---

    @property
    def _trunk_plugin(self):
        return utils.fetch_trunk_plugin()

    def _parent_port_name(self, router_id: str) -> str:
        """Deterministic name for the router's anchor-network parent port."""
        return f"{ANCHOR_PARENT_PORT_NAME_PREFIX}-{router_id}"

    def _trunk_name(self, router_id: str) -> str:
        """Deterministic name for the router's trunk."""
        return f"{TRUNK_NAME_PREFIX}-{router_id}"

    def _gateway_port_for_router(self, router_id: str) -> dict | None:
        """Return the router's Neutron external-gateway port, or None.

        The gateway port is owned by the router (``device_id == router_id``) with
        ``device_owner == network:router_gateway``.
        """
        core_plugin = directory.get_plugin()
        admin_context = n_context.get_admin_context()
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

    def _parent_port_for_router(self, router_id: str) -> dict | None:
        """Return the router's existing anchor-network parent port, or None."""
        core_plugin = directory.get_plugin()
        admin_context = n_context.get_admin_context()
        anchor_network = self._ensure_anchor_network()
        ports = core_plugin.get_ports(
            admin_context,
            filters={
                "name": [self._parent_port_name(router_id)],
                "network_id": [anchor_network["id"]],
            },
        )
        return ports[0] if ports else None

    def _create_parent_port(self, router: dict) -> dict:
        """Create the router's parent port on the anchor network.

        vnic_type=baremetal so Ironic can VIF-attach it to the adopted node.
        Direct core-plugin call (server-side), so extension-default fields are
        supplied explicitly, matching the codebase's other direct port creates.
        """
        core_plugin = directory.get_plugin()
        admin_context = n_context.get_admin_context()
        anchor_network = self._ensure_anchor_network()
        port_name = self._parent_port_name(router["id"])
        LOG.info(
            "Creating Palo Alto anchor parent port %s for router %s",
            port_name,
            router["id"],
        )
        return core_plugin.create_port(
            admin_context,
            {
                "port": {
                    "name": port_name,
                    "network_id": anchor_network["id"],
                    "admin_state_up": True,
                    "device_owner": "",
                    "device_id": router["id"],
                    "mac_address": "",
                    "fixed_ips": [],
                    "project_id": admin_context.project_id or "",
                    portbindings.VNIC_TYPE: portbindings.VNIC_BAREMETAL,
                }
            },
        )

    def _ensure_parent_port(self, router: dict) -> dict:
        """Find-or-create the router's anchor-network parent port (idempotent)."""
        existing = self._parent_port_for_router(router["id"])
        if existing is not None:
            LOG.debug(
                "Reusing Palo Alto anchor parent port %s for router %s",
                existing["id"],
                router["id"],
            )
            return existing
        return self._create_parent_port(router)

    def _fresh_port(self, port_id: str) -> dict:
        """Re-read a port so callers see its current binding profile."""
        core_plugin = directory.get_plugin()
        admin_context = n_context.get_admin_context()
        return core_plugin.get_port(admin_context, port_id)

    def _ensure_parent_vif_attached(self, router: dict, parent_port: dict) -> dict:
        """VIF-attach the parent port to the router's node (idempotent).

        Attaching a single VIF; Ironic binds it to a free baremetal port on the
        node and annotates the Neutron port with local_link_information +
        physical_network and host_id .

        Returns a fresh copy of the parent port reflecting the new binding.
        """
        router_id = router["id"]
        node = self._ironic.node_by_instance_uuid(router_id)
        if node is None:
            raise n_exc.BadRequest(
                resource="router",
                msg=(
                    f"Palo Alto router {router_id} has no adopted Ironic node to "
                    "attach the gateway uplink to."
                ),
            )

        parent_port_id = parent_port["id"]
        if parent_port_id in self._ironic.node_vif_ids(node):
            LOG.debug(
                "Parent port %s already VIF-attached to node %s",
                parent_port_id,
                node.id,
            )
        else:
            self._ironic.attach_vif_to_node(node, parent_port_id)

        fresh = self._fresh_port(parent_port_id)
        self._verify_parent_annotated(router_id, fresh)
        return fresh

    def _verify_parent_annotated(self, router_id: str, parent_port: dict) -> None:
        """Fail fast if Ironic did not annotate the parent port.

        The trunk + undersync need host_id, physical_network and
        local_link_information on the binding profile. If they are missing the
        node's baremetal port most likely has no physical_network (enroll side);
        surface a clear error here instead of a silent no-op at undersync.
        """
        profile = parent_port.get(portbindings.PROFILE) or {}
        missing = [
            name
            for name, value in (
                ("binding:host_id", parent_port.get(portbindings.HOST_ID)),
                ("physical_network", profile.get("physical_network")),
                ("local_link_information", profile.get("local_link_information")),
            )
            if not value
        ]
        if missing:
            raise n_exc.BadRequest(
                resource="router",
                msg=(
                    f"Palo Alto router {router_id} parent port {parent_port['id']} "
                    f"was not annotated by Ironic (missing {', '.join(missing)}); "
                    "check the node's baremetal port has physical_network."
                ),
            )

    def _trunk_for_router(self, router_id: str) -> dict | None:
        """Return the router's existing trunk (by deterministic name), or None."""
        admin_context = n_context.get_admin_context()
        trunks = self._trunk_plugin.get_trunks(
            admin_context, filters={"name": [self._trunk_name(router_id)]}
        )
        return trunks[0] if trunks else None

    def _create_trunk(self, router: dict, parent_port: dict) -> dict:
        """Create the router's trunk with the parent port as its trunk parent."""
        admin_context = n_context.get_admin_context()
        trunk_name = self._trunk_name(router["id"])
        LOG.info(
            "Creating Palo Alto trunk %s on parent port %s for router %s",
            trunk_name,
            parent_port["id"],
            router["id"],
        )
        return self._trunk_plugin.create_trunk(
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

    def _ensure_trunk(self, router: dict, parent_port: dict) -> dict:
        """Find-or-create the router's trunk (idempotent)."""
        existing = self._trunk_for_router(router["id"])
        if existing is not None:
            LOG.debug(
                "Reusing Palo Alto trunk %s for router %s",
                existing["id"],
                router["id"],
            )
            return existing
        return self._create_trunk(router, parent_port)

    def _used_subport_vlans(self, trunk: dict) -> set[int]:
        """Return VLAN segmentation IDs already used on a router trunk."""
        return {
            sp["segmentation_id"]
            for sp in trunk.get("sub_ports", [])
            if sp.get("segmentation_type") == "vlan"
            and sp.get("segmentation_id") is not None
        }

    def _next_available_subport_vlan(
        self, router_id: str, trunk: dict, start_vlan: int
    ) -> int:
        """Pick the first allowed, unused Palo Alto subport VLAN from start."""
        used = self._used_subport_vlans(trunk)
        ranges = sorted(utils.allowed_tenant_vlan_id_ranges())
        for start, end in ranges:
            for vlan in range(max(start, start_vlan), end + 1):
                if vlan not in used:
                    return vlan
        raise NoPaloAltoSubportVlanAvailable(
            router_id=router_id,
            trunk_id=trunk["id"],
            network_segment_ranges=utils.printable_ranges(ranges),
        )

    def _add_router_port_subport(
        self,
        router: dict,
        trunk: dict,
        port: dict,
        segmentation_id: int,
        label: str,
    ):
        """Add a router-owned port to the trunk as a VLAN subport.

        Adding the subport fires the understack trunk driver (SUBPORTS events),
        which allocates the fabric segment, binds it, and calls undersync to
        program the switch. No-ops if the port is already a subport.
        """
        port_id = port["id"]
        existing = {sp["port_id"] for sp in trunk.get("sub_ports", [])}
        if port_id in existing:
            LOG.debug(
                "Palo Alto %s port %s already a subport on trunk %s",
                label,
                port_id,
                trunk["id"],
            )
            return trunk

        admin_context = n_context.get_admin_context()
        LOG.info(
            "Adding Palo Alto %s port %s to trunk %s as VLAN %s subport for router %s",
            label,
            port_id,
            trunk["id"],
            segmentation_id,
            router["id"],
        )
        # The trunk subport validator rejects a port that has device_id set
        # (rules.py check_not_in_use). Router-owned ports have
        # device_id=router_id, so clear it for the add and restore it
        # afterwards so the router keeps its port association.
        original_device_id = port["device_id"]
        original_device_owner = port["device_owner"]
        utils.clear_device_id_for_port(port_id)
        try:
            return self._trunk_plugin.add_subports(
                admin_context,
                trunk["id"],
                {
                    "sub_ports": [
                        {
                            "port_id": port_id,
                            "segmentation_type": "vlan",
                            "segmentation_id": segmentation_id,
                        }
                    ]
                },
            )
        finally:
            utils.set_device_id_and_owner_for_port(
                port_id, original_device_id, original_device_owner
            )

    def _add_gateway_subport(self, router: dict, trunk: dict, gateway_port: dict):
        """Add the gateway port to the trunk as a VLAN subport (idempotent)."""
        port_id = gateway_port["id"]
        if port_id in {sp["port_id"] for sp in trunk.get("sub_ports", [])}:
            LOG.debug(
                "Palo Alto gateway port %s already a subport on trunk %s",
                port_id,
                trunk["id"],
            )
            return trunk
        return self._add_router_port_subport(
            router,
            trunk,
            gateway_port,
            GATEWAY_SUBPORT_VLAN,
            "gateway",
        )

    def _add_interface_subport(self, router: dict, trunk: dict, interface_port: dict):
        """Add a router-interface port to the trunk as a VLAN subport."""
        port_id = interface_port["id"]
        if port_id in {sp["port_id"] for sp in trunk.get("sub_ports", [])}:
            LOG.debug(
                "Palo Alto interface port %s already a subport on trunk %s",
                port_id,
                trunk["id"],
            )
            return trunk
        return self._add_router_port_subport(
            router,
            trunk,
            interface_port,
            self._next_available_subport_vlan(
                router["id"], trunk, INTERFACE_SUBPORT_VLAN_START
            ),
            "interface",
        )

    def _remove_router_port_subport(self, trunk: dict, port_id: str, label: str):
        """Remove a router-owned port from the trunk (idempotent).

        Fires the trunk driver's SUBPORTS delete events, which release the
        fabric segment and update the switchport. No-ops if it is not a subport.
        """
        existing = {sp["port_id"] for sp in trunk.get("sub_ports", [])}
        if port_id not in existing:
            LOG.debug(
                "Palo Alto %s port %s is not a subport on trunk %s; skip removal",
                label,
                port_id,
                trunk["id"],
            )
            return trunk
        admin_context = n_context.get_admin_context()
        LOG.info(
            "Removing Palo Alto %s subport %s from trunk %s",
            label,
            port_id,
            trunk["id"],
        )
        return self._trunk_plugin.remove_subports(
            admin_context,
            trunk["id"],
            {"sub_ports": [{"port_id": port_id}]},
        )

    def _remove_gateway_subport(self, trunk: dict, gateway_port_id: str):
        """Remove the gateway port from the trunk (idempotent)."""
        return self._remove_router_port_subport(trunk, gateway_port_id, "gateway")

    def _remove_interface_subport(self, trunk: dict, interface_port_id: str):
        """Remove a router-interface port from the trunk (idempotent)."""
        return self._remove_router_port_subport(trunk, interface_port_id, "interface")

    def _detach_and_delete_parent(self, router_id: str, parent_id: str) -> None:
        """Detach the parent VIF from the node and delete the parent port."""
        node = self._ironic.node_by_instance_uuid(router_id)
        if node is not None:
            self._ironic.detach_vif_from_node(node, parent_id)
        else:
            LOG.warning(
                "No node found for router %s while detaching parent %s",
                router_id,
                parent_id,
            )
        core_plugin = directory.get_plugin()
        admin_context = n_context.get_admin_context()
        LOG.info("Deleting Palo Alto anchor parent port %s", parent_id)
        core_plugin.delete_port(admin_context, parent_id)

    def _delete_parent_stack_if_unused(self, router_id: str, trunk: dict) -> None:
        """Delete the trunk + parent port only if no subports remain.

        Re-reads the trunk so a subport removed just before this is reflected. If
        other subports are still present (e.g. tenant subnets), leave the trunk
        and parent for them to share.
        """
        admin_context = n_context.get_admin_context()
        fresh = self._trunk_plugin.get_trunk(admin_context, trunk["id"])
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
        self._trunk_plugin.delete_trunk(admin_context, trunk["id"])
        self._detach_and_delete_parent(router_id, parent_id)

    def _cleanup_router_port_attachment(
        self,
        router: dict,
        port_id: str,
        label: str,
    ) -> None:
        """Reverse of the add: remove subport, then tear down the parent stack.

        Handles a partially-built attach too: if a prior add failed after the
        parent port was created/VIF-attached but before the trunk existed, there
        is no trunk to key off, so find and tear down the orphan parent directly.
        """
        router_id = router["id"]
        trunk = self._trunk_for_router(router_id)
        if trunk is None:
            parent = self._parent_port_for_router(router_id)
            if parent is not None:
                LOG.info(
                    "No trunk for Palo Alto router %s; deleting orphan parent %s",
                    router_id,
                    parent["id"],
                )
                self._detach_and_delete_parent(router_id, parent["id"])
            else:
                LOG.debug(
                    "No trunk or parent for Palo Alto router %s; nothing to clean up",
                    router_id,
                )
            return
        self._remove_router_port_subport(trunk, port_id, label)
        self._delete_parent_stack_if_unused(router_id, trunk)

    def _cleanup_gateway_attachment(self, router: dict, gateway_port: dict) -> None:
        """Clean up a gateway port's Palo Alto trunk attachment."""
        self._cleanup_router_port_attachment(router, gateway_port["id"], "gateway")

    def _cleanup_interface_attachment(self, router: dict, interface_port: dict) -> None:
        """Clean up a router-interface port's Palo Alto trunk attachment."""
        self._cleanup_router_port_attachment(router, interface_port["id"], "interface")

    @registry.receives(resources.ROUTER, [events.BEFORE_CREATE])
    def _process_router_create(self, resource, event, trigger, payload=None):
        """Realize the router on hardware, before the router row is created.

        BEFORE_CREATE is a cancellable event published outside the DB
        transaction, and the router UUID is already pre-generated at this point.
        Doing the whole adoption here means every failure (no node, misconfigured
        flavor, or a failed Ironic transition) raises and is returned to the API
        as a clean error with no router created -- and adopt_node_for_router
        rolls a partially-adopted node back to available, so nothing is stranded.
        """
        router = payload.states[0]
        context = payload.context
        if not self._is_palo_alto_provider(context, router):
            return

        resource_class = self._resource_class_for_router(context, router)
        node = self._ironic.available_node_for_resource_class(resource_class)
        if node is None:
            raise NoNetdevNodeAvailable(
                resource_class=resource_class, router_id=router["id"]
            )

        # Ensure the shared anchor network first: it is idempotent and meant to
        # persist, so creating it before adoption never strands an adopted node.
        self._ensure_anchor_network()
        self._ironic.adopt_node_for_router(
            node,
            project_id=router.get("project_id"),
            router_id=router["id"],
            router_name=router.get("name") or router["id"],
        )

        LOG.info(
            "Adopted Ironic node %s for Palo Alto router=%s name=%s project=%s "
            "resource_class=%s",
            node.id,
            router["id"],
            router.get("name"),
            router.get("project_id"),
            resource_class,
        )

    # avoiding Before_delete coz It fires before the "router in use" check
    # releases node for a router that did not get deleted
    @registry.receives(resources.ROUTER, [events.AFTER_DELETE])
    def _process_router_delete(self, resource, event, trigger, payload=None):
        router = payload.states[0]
        context = payload.context
        if not self._is_palo_alto_provider(context, router):
            return

        node = self._ironic.release_node_for_router(router["id"])
        if node is None:
            LOG.warning(
                "Palo Alto router %s deleted but no adopted Ironic node was "
                "found to release",
                router["id"],
            )
            return
        LOG.info(
            "Released Ironic node %s from deleted Palo Alto router %s "
            "(active -> available, cleaning triggered)",
            node.id,
            router["id"],
        )

    def _process_gateway_create(self, resource, event, trigger, payload=None):
        """ROUTER_GATEWAY / AFTER_CREATE (cancellable): wire the gateway.

        Orders the building blocks so the parent port is VIF-bound before the
        subport is added -- the trunk driver only programs the switchport once
        the parent is bound.
        """
        context = payload.context
        router_id = payload.resource_id
        router = self.l3plugin.get_router(context, router_id)
        if not self._is_palo_alto_provider(context, router):
            return

        gateway_port = self._gateway_port_for_router(router_id)
        if gateway_port is None:
            raise n_exc.BadRequest(
                resource="router",
                msg=(
                    f"Palo Alto router {router_id} gateway was created but no "
                    "router gateway port was found."
                ),
            )

        parent = self._ensure_parent_port(router)
        parent = self._ensure_parent_vif_attached(router, parent)
        trunk = self._ensure_trunk(router, parent)
        self._add_gateway_subport(router, trunk, gateway_port)

        LOG.info(
            "Attached Palo Alto router %s gateway port %s via parent %s trunk %s",
            router_id,
            gateway_port["id"],
            parent["id"],
            trunk["id"],
        )

    def _process_gateway_delete(self, resource, event, trigger, payload=None):
        """ROUTER_GATEWAY / BEFORE_DELETE (cancellable): tear down the wiring.

        The gateway port still exists at this point, so we can find it and
        remove its subport before Neutron deletes it.
        """
        context = payload.context
        router_id = payload.resource_id
        router = self.l3plugin.get_router(context, router_id)
        if not self._is_palo_alto_provider(context, router):
            return

        gateway_port = self._gateway_port_for_router(router_id)
        if gateway_port is None:
            LOG.debug(
                "Palo Alto router %s gateway cleanup skipped; gateway port not found",
                router_id,
            )
            return

        self._cleanup_gateway_attachment(router, gateway_port)
        LOG.info(
            "Cleaned Palo Alto router %s gateway attachment (port %s)",
            router_id,
            gateway_port["id"],
        )

    def _process_router_interface_create(self, resource, event, trigger, payload=None):
        """ROUTER_INTERFACE / AFTER_CREATE: wire a subnet interface port."""
        context = payload.context
        router_id = payload.resource_id
        router = self.l3plugin.get_router(context, router_id)
        if not self._is_palo_alto_provider(context, router):
            return

        interface_port = payload.metadata.get("port")
        if not interface_port:
            raise n_exc.BadRequest(
                resource="router",
                msg=(
                    f"Palo Alto router {router_id} interface was created but no "
                    "router interface port was supplied."
                ),
            )
        if interface_port.get("device_owner") not in const.ROUTER_INTERFACE_OWNERS:
            return

        parent = self._ensure_parent_port(router)
        parent = self._ensure_parent_vif_attached(router, parent)
        trunk = self._ensure_trunk(router, parent)
        self._add_interface_subport(router, trunk, interface_port)

        LOG.info(
            "Attached Palo Alto router %s interface port %s via parent %s trunk %s",
            router_id,
            interface_port["id"],
            parent["id"],
            trunk["id"],
        )

    def _process_router_interface_port_delete(
        self, resource, event, trigger, payload=None
    ):
        """PORT / BEFORE_DELETE: remove Palo Alto interface trunk wiring.

        This runs before the trunk plugin's own port-in-use check. That allows
        Neutron to delete a router-interface port that we previously attached as
        a trunk subport.
        """
        port = payload.metadata.get("port") if payload else None
        if not port or port.get("device_owner") not in const.ROUTER_INTERFACE_OWNERS:
            return

        context = payload.context
        router_id = port.get("device_id")
        if not router_id:
            return

        try:
            router = self.l3plugin.get_router(context, router_id)
            is_palo_alto = self._is_palo_alto_provider(context, router)
        except Exception:
            LOG.debug(
                "Skipping Palo Alto interface cleanup for port %s; router %s "
                "could not be confirmed as Palo Alto",
                port["id"],
                router_id,
                exc_info=True,
            )
            return

        if not is_palo_alto:
            return

        self._cleanup_interface_attachment(router, port)
        LOG.info(
            "Cleaned Palo Alto router %s interface attachment (port %s)",
            router_id,
            port["id"],
        )
