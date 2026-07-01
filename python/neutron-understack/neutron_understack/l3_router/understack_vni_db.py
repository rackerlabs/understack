import sqlalchemy as sa
from neutron_lib import constants as n_const
from neutron_lib import exceptions as n_exc
from oslo_config import cfg
from oslo_utils import timeutils

from neutron_understack.db import understack_vni as vni_models

MIN_VNI = getattr(n_const, "MIN_VXLAN_VNI", 1)
MAX_VNI = n_const.MAX_VXLAN_VNI
DEFAULT_VNI_RANGES = [f"{MIN_VNI}:{MAX_VNI}"]


class UnderstackVNIInvalidRange(n_exc.NeutronException):
    message = "Invalid understack_vni.vni_ranges entry %(entry)s: %(reason)s."


class UnderstackVNINotInRange(n_exc.BadRequest):
    message = (
        "VNI %(vni)s is outside the configured Understack VNI ranges " "%(ranges)s."
    )


class UnderstackVNIInUse(n_exc.Conflict):
    message = "Understack VNI %(vni)s is already allocated to router %(router_id)s."


class UnderstackVNIRouterHasVNI(n_exc.Conflict):
    message = (
        "Router %(router_id)s already has Understack VNI %(existing_vni)s; "
        "requested %(requested_vni)s."
    )


class UnderstackVNINoAvailable(n_exc.Conflict):
    message = "No Understack VNI is available in configured ranges %(ranges)s."


def is_auto_vni(vni):
    return vni is n_const.ATTR_NOT_SPECIFIED or vni in (None, 0)


def format_vni_ranges(ranges):
    return ",".join(f"{start}:{end}" for start, end in ranges)


def parse_vni_ranges(vni_ranges):
    parsed = []
    for entry in vni_ranges or []:
        entry = str(entry).strip()  # noqa: PLW2901
        if not entry:
            raise UnderstackVNIInvalidRange(entry=entry, reason="empty range")

        if ":" in entry:
            start_text, end_text = entry.split(":", 1)
        else:
            start_text = end_text = entry

        try:
            start = int(start_text)
            end = int(end_text)
        except ValueError as exc:
            raise UnderstackVNIInvalidRange(
                entry=entry, reason="range bounds must be integers"
            ) from exc

        if start > end:
            raise UnderstackVNIInvalidRange(
                entry=entry, reason="range start must be less than or equal to end"
            )
        if start < MIN_VNI or end > MAX_VNI:
            raise UnderstackVNIInvalidRange(
                entry=entry,
                reason=f"range must be within {MIN_VNI}:{MAX_VNI}",
            )
        parsed.append((start, end))

    if not parsed:
        raise UnderstackVNIInvalidRange(
            entry=",".join(vni_ranges or []), reason="at least one range is required"
        )

    return _merge_ranges(parsed)


def _merge_ranges(ranges):
    merged = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1] + 1:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


class UnderstackVniDbHelper:
    def __init__(self, vni_ranges=None):
        self._vni_ranges = vni_ranges

    @property
    def ranges(self):
        configured_ranges = (
            self._vni_ranges
            if self._vni_ranges is not None
            else cfg.CONF.understack_vni.vni_ranges
        )
        return parse_vni_ranges(configured_ranges)

    def allocate_vni_for_router(self, context, router_id, requested_vni):
        ranges = self.ranges
        existing = self._get_router_allocation(context, router_id)
        if existing:
            if is_auto_vni(requested_vni) or requested_vni == existing.vni:
                return existing.vni
            raise UnderstackVNIRouterHasVNI(
                router_id=router_id,
                existing_vni=existing.vni,
                requested_vni=requested_vni,
            )

        if is_auto_vni(requested_vni):
            return self._allocate_auto_vni(context, router_id, ranges)

        requested_vni = int(requested_vni)
        self._validate_vni_in_ranges(requested_vni, ranges)
        return self._allocate_specific_vni(context, router_id, requested_vni)

    def release_vni_for_router(self, context, router_id):
        allocation = self._get_router_allocation(context, router_id)
        if not allocation:
            return
        allocation.router_id = None
        allocation.released_at = timeutils.utcnow()
        context.session.flush()

    def get_vni_for_router(self, context, router_id):
        allocation = self._get_router_allocation(context, router_id)
        if allocation:
            return allocation.vni
        return None

    def _allocate_auto_vni(self, context, router_id, ranges):
        never_used_vni = self._find_never_used_vni(context, ranges)
        if never_used_vni is not None:
            allocation = vni_models.UnderstackRouterVNIAllocation(
                vni=never_used_vni,
                router_id=router_id,
            )
            context.session.add(allocation)
            context.session.flush()
            return never_used_vni

        released = self._find_released_allocation(context, ranges)
        if released:
            released.router_id = router_id
            released.released_at = None
            context.session.flush()
            return released.vni

        raise UnderstackVNINoAvailable(ranges=format_vni_ranges(ranges))

    def _allocate_specific_vni(self, context, router_id, vni):
        allocation = (
            context.session.query(vni_models.UnderstackRouterVNIAllocation)
            .filter_by(vni=vni)
            .with_for_update()
            .first()
        )
        if allocation:
            if allocation.router_id:
                raise UnderstackVNIInUse(vni=vni, router_id=allocation.router_id)
            allocation.router_id = router_id
            allocation.released_at = None
        else:
            allocation = vni_models.UnderstackRouterVNIAllocation(
                vni=vni,
                router_id=router_id,
            )
            context.session.add(allocation)

        context.session.flush()
        return vni

    def _get_router_allocation(self, context, router_id):
        return (
            context.session.query(vni_models.UnderstackRouterVNIAllocation)
            .filter_by(router_id=router_id)
            .with_for_update()
            .first()
        )

    def _find_never_used_vni(self, context, ranges):
        for start, end in ranges:
            candidate = start
            rows = (
                context.session.query(vni_models.UnderstackRouterVNIAllocation.vni)
                .filter(vni_models.UnderstackRouterVNIAllocation.vni >= start)
                .filter(vni_models.UnderstackRouterVNIAllocation.vni <= end)
                .order_by(vni_models.UnderstackRouterVNIAllocation.vni)
            )
            for (vni,) in rows:
                if vni > candidate:
                    return candidate
                if vni == candidate:
                    candidate += 1
                if candidate > end:
                    break
            if candidate <= end:
                return candidate
        return None

    def _find_released_allocation(self, context, ranges):
        return (
            context.session.query(vni_models.UnderstackRouterVNIAllocation)
            .filter(vni_models.UnderstackRouterVNIAllocation.router_id.is_(None))
            .filter(self._range_filter(ranges))
            .order_by(
                vni_models.UnderstackRouterVNIAllocation.released_at,
                vni_models.UnderstackRouterVNIAllocation.vni,
            )
            .with_for_update()
            .first()
        )

    def _range_filter(self, ranges):
        return sa.or_(
            *[
                vni_models.UnderstackRouterVNIAllocation.vni.between(start, end)
                for start, end in ranges
            ]
        )

    def _validate_vni_in_ranges(self, vni, ranges):
        if not any(start <= vni <= end for start, end in ranges):
            raise UnderstackVNINotInRange(
                vni=vni,
                ranges=format_vni_ranges(ranges),
            )
