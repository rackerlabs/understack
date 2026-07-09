from neutron.services.ovn_l3.service_providers.user_defined import UserDefined
from neutron_lib import constants as n_const
from neutron_lib import exceptions as n_exc
from neutron_lib.callbacks import events
from neutron_lib.callbacks import priority_group
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.db import resource_extend

try:
    from neutron_lib.api.definitions import evpn as evpn_apidef
except ImportError:
    evpn_apidef = None
from neutron_lib.plugins import constants as plugin_constants
from neutron_lib.plugins import directory
from neutron_lib.services import base as service_base
from oslo_config import cfg
from oslo_log import log as logging

from neutron_understack import config
from neutron_understack.api.definitions import understack_vni as apidef
from neutron_understack.l3_router import understack_vni_db

LOG = logging.getLogger(__name__)


class Vrf(UserDefined):
    pass


def _vrf_provider_driver():
    return f"{Vrf.__module__}.{Vrf.__name__}"


def _is_vrf_router(context, router):
    flavor_id = router.get("flavor_id")
    if flavor_id is None or flavor_id is n_const.ATTR_NOT_SPECIFIED:
        return False

    flavor_plugin = directory.get_plugin(plugin_constants.FLAVORS)
    flavor = flavor_plugin.get_flavor(context, flavor_id)
    provider = flavor_plugin.get_flavor_next_provider(context, flavor["id"])[0]
    return str(provider["driver"]) == _vrf_provider_driver()


def _supported_extension_aliases():
    if evpn_apidef is not None:
        return [evpn_apidef.ALIAS]
    return [apidef.ALIAS]


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

        if not _is_vrf_router(payload.context, router):
            if not understack_vni_db.is_auto_vni(requested_vni):
                raise n_exc.BadRequest(
                    resource=apidef.RESOURCE_NAME,
                    msg="evpn_vni can only be set on VRF routers",
                )
            return

        vni = self._vni_db.allocate_vni_for_router(
            payload.context,
            payload.resource_id,
            requested_vni,
        )
        router[apidef.EVPN_VNI] = vni
        LOG.info(
            "Allocated Understack VNI %s for VRF router %s",
            vni,
            payload.resource_id,
        )

    @registry.receives(resources.ROUTER, [events.PRECOMMIT_DELETE])
    def _process_router_delete(self, resource, event, trigger, payload):
        self._vni_db.release_vni_for_router(payload.context, payload.resource_id)
