import logging

from neutron.services.l3_router.service_providers import base
from neutron_lib import constants as const
from neutron_lib.plugins import constants as plugin_constants
from neutron_lib.plugins import directory

LOG = logging.getLogger(__name__)

# Full dotted path as stored in the flavor profile's service_providers table.
# Must match the value in understack/components/neutron/values.yaml.
# SVI_DRIVER = "neutron_understack.l3_router.svi.Svi"


class Svi(base.L3ServiceProvider):
    ha_support = base.OPTIONAL

    def __init__(self, l3_plugin):
        super().__init__(l3_plugin)
        # self._svi_provider = SVI_DRIVER
        self._svi_provider = f"{self.__module__}.{self.__class__.__name__}"
        LOG.info("SVI service provider initialized: driver=%r", self._svi_provider)

    @property
    def _flavor_plugin(self):
        try:
            return self._flavor_plugin_ref
        except AttributeError:
            self._flavor_plugin_ref = directory.get_plugin(plugin_constants.FLAVORS)
            return self._flavor_plugin_ref

    # ATTR_NOT_SPECIFIED “the API field was not provided.”
    def _is_svi_flavor(self, context, router):
        flavor_id = router.get("flavor_id")
        if flavor_id is None or flavor_id is const.ATTR_NOT_SPECIFIED:
            return False

        flavor = self._flavor_plugin.get_flavor(context, flavor_id)
        provider = self._flavor_plugin.get_flavor_next_provider(context, flavor["id"])[
            0
        ]
        is_svi = str(provider["driver"]) == self._svi_provider
        LOG.debug(
            "SVI flavor check: router %s flavor %s driver %s is_svi=%s",
            router.get("id"),
            flavor_id,
            provider["driver"],
            is_svi,
        )
        return is_svi
