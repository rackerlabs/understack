import logging

from neutron.services.l3_router.service_providers import base
from neutron_lib import constants as const
from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.plugins import constants as plugin_constants
from neutron_lib.plugins import directory

LOG = logging.getLogger(__name__)


@registry.has_registry_receivers
class PaloAlto(base.L3ServiceProvider):
    """Stub L3 service provider for the Palo Alto router flavor.

    Inherits from the base L3 service provider instead
    of UserDefined. Routers of this flavor are detected
    via their flavor's service profile driver.
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

    @registry.receives(resources.ROUTER, [events.AFTER_CREATE])
    def _process_router_create(self, resource, event, trigger, payload=None):
        router = payload.states[0]
        context = payload.context
        if not self._is_palo_alto_provider(context, router):
            return
        LOG.info(
            "Palo Alto stub router create: no action taken for router=%s "
            "name=%s project=%s flavor=%s request_id=%s",
            router.get("id"),
            router.get("name"),
            router.get("project_id"),
            router.get("flavor_id"),
            getattr(context, "request_id", None),
        )
