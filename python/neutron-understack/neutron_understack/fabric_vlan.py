from neutron.api import extensions as n_extensions
from neutron.common.ovn import extensions as ovn_extensions
from neutron.db import segments_db
from neutron.db import vni_vlan_allocator
from neutron.db.models import vxlan_vlan_allocations as alloc_models
from neutron.objects.network_segment_range import NetworkSegmentRange
from neutron_lib import constants as p_const
from neutron_lib import context as n_context
from neutron_lib import exceptions as n_exc
from neutron_lib.api import validators
from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.plugins.ml2 import api
from oslo_config import cfg
from oslo_log import log as logging

from neutron_understack import config
from neutron_understack import extensions
from neutron_understack.api.definitions import understack_fabric_vlan as apidef

LOG = logging.getLogger(__name__)

# Runs after ML2's handler (priority 0) and before the segments service plugin
# (default priority) deletes the network's segments, so the VNI is readable.
_DELETE_PRIORITY = 1


class FabricVlanChangeNotAllowed(n_exc.BadRequest):
    message = "fabric_vlan is already %(current)s and cannot be changed or cleared."


class FabricVlanNotVxlan(n_exc.BadRequest):
    message = "fabric_vlan can only be set on VXLAN networks."


class FabricVlanNotInRange(n_exc.BadRequest):
    message = (
        "fabric_vlan %(vlan)s is outside network segment range %(range)s "
        "(%(minimum)s:%(maximum)s)."
    )


class FabricVlanInUse(n_exc.Conflict):
    message = "fabric_vlan %(vlan)s is already in use."

    def __init__(self, min_val, max_val=None):
        # Raised by RangeAllocator as exception_class(min_val, max_val); the
        # range is the single requested VLAN.
        super().__init__(vlan=min_val)


class FabricVlanVniInUse(n_exc.Conflict):
    message = "VNI %(vni)s already has a fabric_vlan."


class FabricVlanRangeNotFound(n_exc.NeutronException):
    message = (
        "Expected exactly one VLAN network segment range on physical network "
        "%(physnet)s ([ml2_understack] fabric_vlan_physical_network), found "
        "%(count)s."
    )


def fabric_vlan_physnet() -> str:
    """Physnet of the fabric range, and scope of its vni_vlan_mapping rows.

    Each network has one vni_vlan_mapping, pairing its VXLAN VNI with its
    fabric_vlan, in vni_allocations and vlan_allocations under this physnet.
    """
    return cfg.CONF.ml2_understack.fabric_vlan_physical_network


def find_fabric_vlan_range(context) -> NetworkSegmentRange:
    physnet = fabric_vlan_physnet()
    ranges = NetworkSegmentRange.get_objects(
        context, network_type=p_const.TYPE_VLAN, physical_network=physnet
    )
    if len(ranges) != 1:
        raise FabricVlanRangeNotFound(physnet=physnet, count=len(ranges))
    return ranges[0]


def _vxlan_vni(context, network_id: str) -> int | None:
    for segment in segments_db.get_network_segments(context, network_id):
        if segment[api.NETWORK_TYPE] == p_const.TYPE_VXLAN:
            return segment[api.SEGMENTATION_ID]
    return None


def _fabric_vlan_mapping(session, vni: int):
    """Return (mapping_id, vlan_id) for the VNI, or None."""
    return (
        session.query(
            alloc_models.VNIVLANMapping.id, alloc_models.VLANAllocation.vlan_id
        )
        .join(
            alloc_models.VNIAllocation,
            alloc_models.VNIAllocation.id
            == alloc_models.VNIVLANMapping.vni_allocation_id,
        )
        .join(
            alloc_models.VLANAllocation,
            alloc_models.VLANAllocation.id
            == alloc_models.VNIVLANMapping.vlan_allocation_id,
        )
        .filter(
            alloc_models.VNIAllocation.vni == vni,
            alloc_models.VNIAllocation.physnet == fabric_vlan_physnet(),
        )
        .first()
    )


_allocator = vni_vlan_allocator.VNIVLANAllocator(
    vni_exhausted_exc=FabricVlanInUse,
    vlan_exhausted_exc=FabricVlanInUse,
    vni_in_use_exc=FabricVlanVniInUse,
)


def reserve_fabric_vlan(
    context, ns_range: NetworkSegmentRange, vni: int, vlan: int
) -> None:
    if not ns_range.minimum <= vlan <= ns_range.maximum:
        raise FabricVlanNotInRange(
            vlan=vlan,
            range=ns_range.name or ns_range.id,
            minimum=ns_range.minimum,
            maximum=ns_range.maximum,
        )
    # A one-VLAN range: the VLAN is either claimed or FabricVlanInUse.
    physnet = fabric_vlan_physnet()
    _allocator.allocate_specific_vni(
        context, vni, physnet, vni_vlan_allocator.ScopedRange(vlan, vlan, physnet)
    )


def release_fabric_vlan(context, network_id: str) -> None:
    vni = _vxlan_vni(context, network_id)
    if vni is None:
        return
    mapping = _fabric_vlan_mapping(context.session, vni)
    if mapping:
        _allocator.deallocate(context, mapping.id)


class UnderstackFabricVlanExtensionDriver(api.ExtensionDriver):
    """Pins a VXLAN network to one VLAN on every physnet it binds to.

    The VLAN comes from a dedicated network segment range and is held in
    neutron's vni_vlan_mapping, which keeps it unique across networks.
    UnderstackDriver requests it for each dynamic segment.
    """

    def initialize(self):
        config.register_ml2_understack_opts(cfg.CONF)
        # Neutron adds extension paths for service plugins, not ML2 drivers.
        n_extensions.append_api_extensions_path(list(extensions.__path__))
        registry.subscribe(
            self._network_precommit_delete,
            resources.NETWORK,
            events.PRECOMMIT_DELETE,
            priority=_DELETE_PRIORITY,
        )
        # The OVN mech driver drops any alias not in this allowlist from
        # Ml2Plugin.supported_extension_aliases, which leaves the attribute
        # unregistered ("Unrecognized attribute(s) 'fabric_vlan'").
        if apidef.ALIAS not in ovn_extensions.ML2_SUPPORTED_API_EXTENSIONS:
            ovn_extensions.ML2_SUPPORTED_API_EXTENSIONS.append(apidef.ALIAS)
        self._range_id = None
        try:
            self._range_id = find_fabric_vlan_range(n_context.get_admin_context()).id
        except FabricVlanRangeNotFound as exc:
            # Non-fatal: the range may be created after neutron starts.
            LOG.warning("%s Looking it up again on first use.", exc)
        LOG.info("Understack fabric VLAN extension driver initialized")

    def _fabric_vlan_range(self, context) -> NetworkSegmentRange:
        """Return the configured range by its cached ID.

        Caching only the ID keeps edits to the bounds live. Falls back to a
        name lookup when the ID is unset or the range was deleted.
        """
        # Elevated, not a new admin context: the range is admin-owned and the
        # query must run in the caller's transaction.
        context = context.elevated()
        if self._range_id is not None:
            ns_range = NetworkSegmentRange.get_object(context, id=self._range_id)
            if ns_range is not None:
                return ns_range
        ns_range = find_fabric_vlan_range(context)
        self._range_id = ns_range.id
        return ns_range

    @property
    def extension_alias(self):
        return apidef.ALIAS

    def process_create_network(self, plugin_context, data, result):
        self._apply(plugin_context, data, result)

    def process_update_network(self, plugin_context, data, result):
        self._apply(plugin_context, data, result)

    def _apply(self, plugin_context, data, result):
        """Reserve the requested fabric_vlan; unset leaves the network alone.

        A network may gain a fabric_vlan after it was created. Segments
        already bound keep their VLAN; the fabric_vlan is requested for the
        dynamic segments created from then on. Once set it cannot change.
        """
        vlan = data.get(apidef.FABRIC_VLAN, p_const.ATTR_NOT_SPECIFIED)
        vni = _vxlan_vni(plugin_context, result["id"])
        mapping = (
            _fabric_vlan_mapping(plugin_context.session, vni)
            if vni is not None
            else None
        )
        current = mapping.vlan_id if mapping else None
        result[apidef.FABRIC_VLAN] = current

        if not validators.is_attr_set(vlan):
            # An explicit null is a request to clear it.
            if vlan is None and current is not None:
                raise FabricVlanChangeNotAllowed(current=current)
            return

        if current is not None:
            if vlan != current:
                raise FabricVlanChangeNotAllowed(current=current)
            return

        if vni is None:
            raise FabricVlanNotVxlan()

        reserve_fabric_vlan(
            plugin_context, self._fabric_vlan_range(plugin_context), vni, vlan
        )
        result[apidef.FABRIC_VLAN] = vlan
        LOG.info("Reserved fabric_vlan %s for network %s", vlan, result["id"])

    def extend_network_dict(self, session, base_model, result):
        # Network.segments is selectin loaded; this costs one query per VXLAN
        # network.
        vni = next(
            (
                segment.segmentation_id
                for segment in base_model.segments
                if segment.network_type == p_const.TYPE_VXLAN and not segment.is_dynamic
            ),
            None,
        )
        mapping = _fabric_vlan_mapping(session, vni) if vni is not None else None
        result[apidef.FABRIC_VLAN] = mapping.vlan_id if mapping else None

    def _network_precommit_delete(self, resource, event, trigger, payload):
        release_fabric_vlan(payload.context, payload.resource_id)
