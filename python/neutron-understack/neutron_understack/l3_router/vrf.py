from neutron.services.ovn_l3.service_providers.user_defined import UserDefined
from neutron_lib import constants as n_const
from neutron_lib import exceptions as n_exc
from neutron_lib.callbacks import events
from neutron_lib.callbacks import priority_group
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.db import resource_extend
from neutron_lib.plugins import constants as plugin_constants
from neutron_lib.plugins import directory
from neutron_lib.services import base as service_base
from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils

from neutron_understack import config
from neutron_understack import evpn_compat
from neutron_understack.api.definitions import understack_vni as apidef
from neutron_understack.l3_router import understack_vni_db

LOG = logging.getLogger(__name__)

# Service-profile metainfo key (and its allowed values) that toggles how the
# Understack VNI plugin treats ``evpn_vni`` for routers of a given flavor. The
# operator sets it as JSON in the flavor's service profile metainfo, e.g.
# ``{"vni_alloc": "auto"}``.
VNI_ALLOC_KEY = "vni_alloc"
# ``off``  -- never allocate a VNI; reject any explicitly supplied evpn_vni.
VNI_ALLOC_OFF = "off"
# ``on``   -- allocate only an explicitly supplied evpn_vni; never auto-allocate.
VNI_ALLOC_ON = "on"
# ``auto`` -- auto-allocate a VNI when none is supplied; honor an explicit one.
VNI_ALLOC_AUTO = "auto"
# When a flavor carries no metainfo toggle (or has no flavor at all) we must not
# allocate. This is what keeps non-VRF flavors (e.g. Palo Alto) from getting a
# VNI now that the evpn_vni attribute default is ATTR_NOT_SPECIFIED.
VNI_ALLOC_DEFAULT = VNI_ALLOC_OFF
_VALID_VNI_ALLOC = (VNI_ALLOC_OFF, VNI_ALLOC_ON, VNI_ALLOC_AUTO)


class Vrf(UserDefined):
    pass


def _vrf_provider_driver():
    return f"{Vrf.__module__}.{Vrf.__name__}"


def _service_profile_metainfo(context, flavor_plugin, flavor):
    """Return the parsed metainfo dict for a flavor's service profile.

    metainfo is stored as a (nullable) JSON string on the service profile.
    Returns an empty dict when there is no profile, no metainfo, or the
    metainfo is not valid JSON describing an object.
    """
    for sp_id in flavor.get("service_profiles", []):
        sp = flavor_plugin.get_service_profile(context, sp_id)
        raw = sp.get("metainfo")
        if not raw:
            continue
        if isinstance(raw, dict):
            return raw
        try:
            parsed = jsonutils.loads(raw)
        except (ValueError, TypeError):
            LOG.warning(
                "Ignoring non-JSON metainfo on service profile %s: %r",
                sp_id,
                raw,
            )
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _router_vni_alloc(context, router):
    """Resolve the evpn_vni allocation mode for a router from its flavor.

    Returns one of ``off``/``on``/``auto``. A router with no flavor, no
    service-profile metainfo, or an unrecognized value defaults to ``off``.
    """
    flavor_id = router.get("flavor_id")
    if flavor_id is None or flavor_id is n_const.ATTR_NOT_SPECIFIED:
        return VNI_ALLOC_OFF

    flavor_plugin = directory.get_plugin(plugin_constants.FLAVORS)
    flavor = flavor_plugin.get_flavor(context, flavor_id)
    metainfo = _service_profile_metainfo(context, flavor_plugin, flavor)

    mode = str(metainfo.get(VNI_ALLOC_KEY, VNI_ALLOC_DEFAULT)).lower()
    if mode not in _VALID_VNI_ALLOC:
        LOG.warning(
            "Router flavor %s has invalid %s=%r in service-profile metainfo; "
            "defaulting to %s",
            flavor_id,
            VNI_ALLOC_KEY,
            mode,
            VNI_ALLOC_DEFAULT,
        )
        return VNI_ALLOC_DEFAULT
    return mode


def _supported_extension_aliases():
    # Advertise whichever extension provides the router evpn_vni attribute:
    # core's ``evpn`` when core owns it, otherwise Understack's own.
    return [evpn_compat.api_definition().ALIAS]


@resource_extend.has_resource_extenders
@registry.has_registry_receivers
class UnderstackVniPlugin(service_base.ServicePluginBase):
    supported_extension_aliases = _supported_extension_aliases()

    __native_pagination_support = True
    __native_sorting_support = True

    def __init__(self):
        super().__init__()
        config.register_understack_vni_opts(cfg.CONF)
        self._vni_db = understack_vni_db.UnderstackVniDbHelper()
        LOG.info("Starting Understack VNI service plugin")

    @classmethod
    def get_plugin_type(cls):
        return "UNDERSTACK_VNI"

    def get_plugin_description(self):
        return "Understack router VNI allocation plugin"

    @staticmethod
    @resource_extend.extends([apidef.COLLECTION_NAME])
    def _extend_router_dict(router_res, router_db):
        allocation = None
        if hasattr(router_db, "get"):
            allocation = router_db.get("understack_vni_allocation")
        if allocation is None:
            allocation = getattr(router_db, "understack_vni_allocation", None)

        router_res[apidef.EVPN_VNI] = (
            allocation.vni if allocation and allocation.router_id else None
        )
        return router_res

    @registry.receives(
        resources.ROUTER,
        [events.PRECOMMIT_CREATE],
        priority_group.PRIORITY_ROUTER_EXTENDED_ATTRIBUTE,
    )
    def _process_router_create(self, resource, event, trigger, payload):
        router = payload.latest_state
        requested_vni = router.get(
            apidef.EVPN_VNI,
            n_const.ATTR_NOT_SPECIFIED,
        )
        explicit = not understack_vni_db.is_auto_vni(requested_vni)

        mode = _router_vni_alloc(payload.context, router)

        if mode == VNI_ALLOC_OFF:
            if explicit:
                raise n_exc.BadRequest(
                    resource=apidef.RESOURCE_NAME,
                    msg="evpn_vni cannot be set on routers of this flavor",
                )
            # Leave evpn_vni as ATTR_NOT_SPECIFIED so neither Understack nor
            # neutron core allocates a VNI for this router.
            return

        if mode == VNI_ALLOC_ON and not explicit:
            # Supplied-VNIs-only: nothing to allocate when none was supplied.
            return

        # ``auto`` (with or without an explicit VNI) or ``on`` with an explicit
        # VNI: allocate_vni_for_router handles both auto-pick and specific-VNI.
        vni = self._vni_db.allocate_vni_for_router(
            payload.context,
            payload.resource_id,
            requested_vni,
        )
        router[apidef.EVPN_VNI] = vni
        LOG.info(
            "Allocated Understack VNI %s for router %s (vni_alloc=%s)",
            vni,
            payload.resource_id,
            mode,
        )

    @registry.receives(resources.ROUTER, [events.PRECOMMIT_DELETE])
    def _process_router_delete(self, resource, event, trigger, payload):
        self._vni_db.release_vni_for_router(payload.context, payload.resource_id)
