from typing import ClassVar

import nova.conf
from nova import context as nova_context
from nova.scheduler import filters
from nova.scheduler.client import report as report_client
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
CONF = nova.conf.CONF


class TraitRequiredFilter(filters.BaseHostFilter):
    """Filter hosts based on custom traits passed via scheduler hints.

    Accepts scheduler hints in the form:
        trait:CUSTOM_<NAME>=required

    Only hosts whose resource provider reports the requested trait(s)
    will pass the filter. If no trait hints are provided, all hosts pass.

    Traits are fetched from the Placement API using the resource provider
    UUID associated with each host.

    Usage:
        openstack server create ... --hint trait:CUSTOM_CAB_A1_1=required
    """

    # Scheduler hints can differ per request, so this filter must
    # run against every host for each request.
    run_filter_once_per_request = False

    # Cache of {rp_uuid: set(traits)} populated per scheduling pass.
    # This avoids repeated Placement API calls for the same provider
    # within a single filter run.
    _traits_cache: ClassVar[dict[str, set[str]]] = {}

    def host_passes(self, host_state, spec_obj):
        requested_traits = set()

        hints = spec_obj.scheduler_hints or {}
        for key, values in hints.items():
            if not key.startswith("trait:"):
                continue
            trait_name = key.split("trait:", 1)[1]
            if not trait_name.startswith("CUSTOM_"):
                continue
            # values is a list; check if 'required' is among them
            if "required" in values:
                requested_traits.add(trait_name)

        if not requested_traits:
            return True

        host_traits = self._get_traits_for_host(host_state)
        missing = requested_traits - host_traits

        if missing:
            LOG.debug(
                "%(host)s fails TraitRequiredFilter: missing %(missing)s",
                {"host": host_state.host, "missing": missing},
            )
            return False

        return True

    def _get_traits_for_host(self, host_state):
        """Get traits for a host's resource provider from Placement.

        Uses a per-instance cache to avoid repeated API calls within
        the same scheduling pass.
        """
        rp_uuid = host_state.uuid
        if rp_uuid in self._traits_cache:
            return self._traits_cache[rp_uuid]

        try:
            client = report_client.report_client_singleton()
            context = nova_context.get_admin_context()
            trait_info = client.get_provider_traits(context, rp_uuid)
            traits = trait_info.traits
        except Exception:
            LOG.warning(
                "Could not retrieve traits for host %(host)s "
                "(rp_uuid=%(uuid)s) from Placement API.",
                {"host": host_state.host, "uuid": rp_uuid},
            )
            traits = set()

        self._traits_cache[rp_uuid] = traits
        return traits

    def filter_all(self, filter_obj_list, spec_obj):
        """Override to clear the traits cache before each filter pass."""
        self._traits_cache = {}
        return super().filter_all(filter_obj_list, spec_obj)


def all_filters():
    """Return all standard Nova filters plus Understack custom filters.

    This function is used as the value for [filter_scheduler]available_filters
    to work around OpenStack Helm's inability to render MultiStrOpt values
    (it joins YAML lists into a single comma-separated line).

    By pointing available_filters to this single function path, we avoid
    needing multiple available_filters lines.
    """
    from nova.scheduler.filters import all_filters as nova_all_filters

    return [*nova_all_filters(), TraitRequiredFilter]
