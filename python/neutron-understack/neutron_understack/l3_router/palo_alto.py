import json
import logging
import weakref

from neutron.objects import router as l3_obj
from neutron.services.l3_router.service_providers import base
from neutron_lib import constants as const
from neutron_lib import exceptions as n_exc
from neutron_lib.callbacks import events
from neutron_lib.callbacks import priority_group
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.plugins import constants as plugin_constants
from neutron_lib.plugins import directory

from neutron_understack.ironic import IronicClient
from neutron_understack.l3_router.palo_alto_wiring import PaloAltoWiring

LOG = logging.getLogger(__name__)


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


# BadRequest -> HTTP 400: the gateway event fired without a gateway port.
class PaloAltoGatewayPortNotFound(n_exc.BadRequest):
    message = (
        "Palo Alto router %(router_id)s gateway was created but no router "
        "gateway port was found."
    )


# BadRequest -> HTTP 400: the interface event carried no port.
class PaloAltoInterfacePortMissing(n_exc.BadRequest):
    message = (
        "Palo Alto router %(router_id)s interface attachment has no router "
        "interface port."
    )


def _parse_metainfo(raw) -> dict:
    """Service-profile metainfo is stored as a JSON string."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
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
    detected via their flavor's service profile driver. Gateway and interface
    wiring is delegated to PaloAltoWiring.
    """

    ha_support = base.OPTIONAL

    def __init__(self, l3_plugin):
        super().__init__(l3_plugin)
        self._palo_alto_provider = f"{__name__}.{self.__class__.__name__}"
        self._interface_snapshots = weakref.WeakKeyDictionary()
        self._wiring = PaloAltoWiring(ironic=lambda: self._ironic)
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
            events.BEFORE_CREATE,
            priority=priority_group.PRIORITY_ROUTER_DRIVER,
            cancellable=True,
        )
        registry.subscribe(
            self._process_router_interface_abort,
            resources.ROUTER_INTERFACE,
            events.ABORT_CREATE,
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

    def _is_palo_alto_provider(self, context, router) -> bool:
        flavor_id = router.get("flavor_id")
        actual_driver = None
        if flavor_id is not None and flavor_id is not const.ATTR_NOT_SPECIFIED:
            flavor = self._flavor_plugin.get_flavor(context, flavor_id)
            providers = self._flavor_plugin.get_flavor_next_provider(
                context, flavor["id"]
            )
            actual_driver = str(providers[0]["driver"])
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

    def _palo_alto_router(self, context, router_id: str) -> dict | None:
        """Return the router if it uses the Palo Alto flavor, else None."""
        router = self.l3plugin.get_router(context, router_id)
        if not self._is_palo_alto_provider(context, router):
            return None
        return router

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
        self._wiring._ensure_anchor_network()
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

    # Use AFTER_DELETE: BEFORE_DELETE precedes the router-in-use check and
    # could release the node even when deletion is rejected.
    @registry.receives(resources.ROUTER, [events.AFTER_DELETE])
    def _process_router_delete(self, resource, event, trigger, payload=None):
        router = payload.states[0]
        context = payload.context
        if not self._is_palo_alto_provider(context, router):
            return

        result = self._ironic.release_node_for_router(router["id"])
        if result.node is None:
            LOG.warning(
                "Palo Alto router %s deleted but no adopted Ironic node was "
                "found to release",
                router["id"],
            )
            return
        if not result.released:
            LOG.warning(
                "Release of Ironic node %s from deleted Palo Alto router %s "
                "is incomplete; reconciliation will retry it",
                result.node.id,
                router["id"],
            )
            return
        LOG.info(
            "Released Ironic node %s from deleted Palo Alto router %s; "
            "ownership cleanup completed",
            result.node.id,
            router["id"],
        )

    def _process_gateway_create(self, resource, event, trigger, payload=None):
        """ROUTER_GATEWAY / AFTER_CREATE (cancellable): wire the gateway.

        Orders the building blocks so the parent port is VIF-bound before the
        subport is added -- the trunk driver only programs the switchport once
        the parent is bound.
        """
        router_id = payload.resource_id
        router = self._palo_alto_router(payload.context, router_id)
        if router is None:
            return

        gateway_port = self._wiring._gateway_port_for_router(router_id)
        if gateway_port is None:
            raise PaloAltoGatewayPortNotFound(router_id=router_id)

        parent = self._wiring._ensure_parent_port(router)
        parent = self._wiring._ensure_parent_vif_attached(router, parent)
        trunk = self._wiring._ensure_trunk(router, parent)
        self._wiring._add_gateway_subport(router, trunk, gateway_port)

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
        router_id = payload.resource_id
        router = self._palo_alto_router(payload.context, router_id)
        if router is None:
            return

        gateway_port = self._wiring._gateway_port_for_router(router_id)
        if gateway_port is None:
            LOG.debug(
                "Palo Alto router %s gateway cleanup skipped; gateway port not found",
                router_id,
            )
            return

        self._wiring._cleanup_gateway_attachment(router, gateway_port)
        LOG.info(
            "Cleaned Palo Alto router %s gateway attachment (port %s)",
            router_id,
            gateway_port["id"],
        )

    def _process_router_interface_create(self, resource, event, trigger, payload=None):
        """Wire the interface before Neutron commits its RouterPort association."""
        router_id = payload.resource_id
        router = self._palo_alto_router(payload.context, router_id)
        if router is None:
            return

        interface_port = payload.metadata.get("port")
        if not interface_port:
            raise PaloAltoInterfacePortMissing(router_id=router_id)
        if interface_port.get("device_owner") not in const.ROUTER_INTERFACE_OWNERS:
            return

        self._interface_snapshots[payload] = (
            self._wiring._snapshot_interface_attachment(router_id, interface_port["id"])
        )
        try:
            parent = self._wiring._ensure_parent_port(router)
            parent = self._wiring._ensure_parent_vif_attached(router, parent)
            trunk = self._wiring._ensure_trunk(router, parent)
            self._wiring._add_interface_subport(router, trunk, interface_port)
        except Exception:
            # Attach-by-port is reverted with a port update by Neutron, so it
            # cannot rely on PORT/BEFORE_DELETE to undo partial realization.
            self._rollback_interface_attachment(payload)
            raise

        LOG.info(
            "Attached Palo Alto router %s interface port %s via parent %s trunk %s",
            router_id,
            interface_port["id"],
            parent["id"],
            trunk["id"],
        )

    def _rollback_interface_attachment(self, payload) -> None:
        """Undo this request's changes, including calls that failed postcommit."""
        snapshot = self._interface_snapshots.get(payload)
        if snapshot is None:
            return
        try:
            self._wiring._undo_interface_attachment(snapshot)
        except Exception:
            # Preserve the original attach error. Keep the snapshot so the
            # subsequent ABORT_CREATE can retry compensation if it failed here.
            LOG.exception(
                "Failed to roll back Palo Alto router %s interface port %s; "
                "attachment cleanup is incomplete",
                snapshot.router_id,
                snapshot.port_id,
            )
            return
        self._interface_snapshots.pop(payload, None)

    def _process_router_interface_abort(self, resource, event, trigger, payload=None):
        # The registry continues invoking callbacks after validation errors. An
        # error in another subscriber must unwind even a successful attachment.
        if payload is not None:
            self._rollback_interface_attachment(payload)

    def _process_router_interface_port_delete(
        self, resource, event, trigger, payload=None
    ):
        """PORT / BEFORE_DELETE: remove Palo Alto interface trunk wiring.

        This runs before the trunk plugin's own port-in-use check. That allows
        Neutron to delete a router-interface port that we previously attached as
        a trunk subport.
        """
        if payload is None or payload.metadata.get("port_check") is not False:
            return
        port = payload.metadata.get("port")
        if not port or port.get("device_owner") not in const.ROUTER_INTERFACE_OWNERS:
            return

        context = payload.context
        router_id = port.get("device_id")
        if not router_id:
            return

        try:
            router = self._palo_alto_router(context, router_id)
        except Exception:
            LOG.debug(
                "Skipping Palo Alto interface cleanup for port %s; router %s "
                "could not be confirmed as Palo Alto",
                port["id"],
                router_id,
                exc_info=True,
            )
            return

        if router is None:
            return

        # Neutron also deletes newly-created ports when attachment aborts. That
        # request already compensated its changes; it must not remove a shared
        # stack which existed beforehand and has no RouterPort for this port.
        if not l3_obj.RouterPort.objects_exist(
            context, router_id=router_id, port_id=port["id"]
        ):
            return

        self._wiring._cleanup_interface_attachment(router, port)
        LOG.info(
            "Cleaned Palo Alto router %s interface attachment (port %s)",
            router_id,
            port["id"],
        )
