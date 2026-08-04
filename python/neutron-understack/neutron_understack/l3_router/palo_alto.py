import json
import logging

from neutron.services.l3_router.service_providers import base
from neutron_lib import constants as const
from neutron_lib import context as n_context
from neutron_lib import exceptions as n_exc
from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.plugins import constants as plugin_constants
from neutron_lib.plugins import directory

from neutron_understack.ironic import IronicClient

LOG = logging.getLogger(__name__)

# Single shared sentinel network owned by the router flavor code.
ANCHOR_NETWORK_NAME = "l2vni_subport_anchor_network"


class NoNetdevNodeAvailable(n_exc.NeutronException):
    message = (
        "No Ironic node with resource_class %(resource_class)s is available to "
        "realize router %(router_id)s."
    )


class PaloAltoFlavorMisconfigured(n_exc.NeutronException):
    message = (
        "Router %(router_id)s flavor %(flavor_id)s does not define a "
        "resource_class in its service profile metainfo."
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
