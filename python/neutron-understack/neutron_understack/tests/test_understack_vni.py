from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from neutron_lib import constants as n_const
from neutron_lib.db import api as db_api
from oslo_db import exception as db_exc
from oslo_serialization import jsonutils
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from neutron_understack.api.definitions import understack_vni as apidef
from neutron_understack.l3_router import understack_vni_db
from neutron_understack.l3_router import vrf


class FakeFlavorPlugin:
    """Minimal flavor plugin exposing a single service profile's metainfo.

    ``metainfo`` is passed through verbatim (a JSON string, matching how
    neutron stores it on the service profile, or a dict) so tests exercise the
    real metainfo parsing path in ``vrf._service_profile_metainfo``.
    """

    def __init__(self, metainfo=None):
        self._metainfo = metainfo

    def get_flavor(self, _context, flavor_id):
        return {"id": flavor_id, "service_profiles": ["sp-1"]}

    def get_service_profile(self, _context, _sp_id):
        return {"id": "sp-1", "metainfo": self._metainfo}


def _mode_metainfo(mode):
    """Build a service-profile metainfo JSON string selecting an evpn_vni mode."""
    return jsonutils.dumps({vrf.VNI_ALLOC_KEY: mode})


@pytest.fixture
def db_context():
    engine = create_engine("sqlite:///:memory:")
    session = sessionmaker(bind=engine)()
    session.execute(
        sa.text(
            """
            CREATE TABLE understack_router_vni_allocations (
                vni INTEGER NOT NULL PRIMARY KEY,
                router_id VARCHAR(36) NULL UNIQUE,
                allocated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                released_at DATETIME NULL
            )
            """
        )
    )
    session.commit()
    yield SimpleNamespace(session=session)
    session.close()
    engine.dispose()


def test_parse_vni_ranges_merges_overlapping_ranges():
    assert understack_vni_db.parse_vni_ranges(["200:202", "100", "101:103"]) == [
        (100, 103),
        (200, 202),
    ]


def test_parse_vni_ranges_rejects_invalid_range():
    with pytest.raises(understack_vni_db.UnderstackVNIInvalidRange):
        understack_vni_db.parse_vni_ranges(["200:100"])


def test_auto_allocation_uses_never_used_vnis_before_released_vnis(db_context):
    helper = understack_vni_db.UnderstackVniDbHelper(vni_ranges=["100:102"])

    assert helper.allocate_vni_for_router(db_context, "router-1", None) == 100
    assert helper.allocate_vni_for_router(db_context, "router-2", 0) == 101

    helper.release_vni_for_router(db_context, "router-1")

    assert helper.allocate_vni_for_router(db_context, "router-3", 0) == 102
    assert helper.allocate_vni_for_router(db_context, "router-4", 0) == 100


def test_specific_allocation_can_reuse_released_vni(db_context):
    helper = understack_vni_db.UnderstackVniDbHelper(vni_ranges=["100:101"])

    assert helper.allocate_vni_for_router(db_context, "router-1", 100) == 100
    helper.release_vni_for_router(db_context, "router-1")

    assert helper.allocate_vni_for_router(db_context, "router-2", 100) == 100


def test_specific_allocation_rejects_active_vni(db_context):
    helper = understack_vni_db.UnderstackVniDbHelper(vni_ranges=["100:101"])

    helper.allocate_vni_for_router(db_context, "router-1", 100)

    with pytest.raises(understack_vni_db.UnderstackVNIInUse):
        helper.allocate_vni_for_router(db_context, "router-2", 100)


def test_auto_allocation_reports_exhaustion(db_context):
    helper = understack_vni_db.UnderstackVniDbHelper(vni_ranges=["100"])

    helper.allocate_vni_for_router(db_context, "router-1", 0)

    with pytest.raises(understack_vni_db.UnderstackVNINoAvailable):
        helper.allocate_vni_for_router(db_context, "router-2", 0)


def test_router_create_retries_auto_allocation_vni_race(mocker, db_context):
    helper = understack_vni_db.UnderstackVniDbHelper(vni_ranges=["100:101"])
    plugin = vrf.UnderstackVniPlugin.__new__(vrf.UnderstackVniPlugin)
    plugin._vni_db = helper
    mocker.patch.object(
        vrf.directory,
        "get_plugin",
        return_value=FakeFlavorPlugin(_mode_metainfo(vrf.VNI_ALLOC_AUTO)),
    )
    mocker.patch("oslo_db.api.time.sleep")

    original_flush = db_context.session.flush
    original_rollback = db_context.session.rollback
    collided = False
    winner_inserted = False

    def flush_with_collision(*args, **kwargs):
        nonlocal collided
        if not collided:
            collided = True
            raise db_exc.DBDuplicateEntry(columns=["vni"], value=100)
        return original_flush(*args, **kwargs)

    def rollback_and_insert_winner():
        nonlocal winner_inserted
        original_rollback()
        if collided and not winner_inserted:
            db_context.session.execute(
                sa.text(
                    """
                    INSERT INTO understack_router_vni_allocations
                        (vni, router_id)
                    VALUES (:vni, :router_id)
                    """
                ),
                {"vni": 100, "router_id": "router-racer"},
            )
            db_context.session.commit()
            winner_inserted = True

    mocker.patch.object(db_context.session, "flush", side_effect=flush_with_collision)
    mocker.patch.object(
        db_context.session, "rollback", side_effect=rollback_and_insert_winner
    )

    @db_api.retry_if_session_inactive()
    def create_router(context, plugin):
        router = {
            "id": "router-1",
            "flavor_id": "flavor-1",
            apidef.EVPN_VNI: 0,
        }
        payload = SimpleNamespace(
            context=context,
            resource_id="router-1",
            latest_state=router,
        )

        plugin._process_router_create(None, None, None, payload)
        return payload.latest_state[apidef.EVPN_VNI]

    assert create_router(db_context, plugin) == 101

    rows = db_context.session.execute(
        sa.text(
            """
            SELECT vni, router_id
            FROM understack_router_vni_allocations
            ORDER BY vni
            """
        )
    ).fetchall()
    assert rows == [(100, "router-racer"), (101, "router-1")]


def _make_plugin(mocker, metainfo, allocate_return=500):
    mocker.patch.object(
        vrf.directory,
        "get_plugin",
        return_value=FakeFlavorPlugin(metainfo),
    )
    plugin = vrf.UnderstackVniPlugin.__new__(vrf.UnderstackVniPlugin)
    plugin._vni_db = mocker.Mock()
    plugin._vni_db.allocate_vni_for_router.return_value = allocate_return
    return plugin


def _create_payload(evpn_vni=n_const.ATTR_NOT_SPECIFIED, flavor_id="flavor-1"):
    latest_state = {"id": "router-1", "flavor_id": flavor_id}
    if evpn_vni is not n_const.ATTR_NOT_SPECIFIED:
        latest_state[apidef.EVPN_VNI] = evpn_vni
    return SimpleNamespace(
        context="context",
        resource_id="router-1",
        latest_state=latest_state,
    )


def test_auto_mode_allocates_vni_without_supplied_value(mocker):
    plugin = _make_plugin(mocker, _mode_metainfo(vrf.VNI_ALLOC_AUTO))
    payload = _create_payload()

    plugin._process_router_create(None, None, None, payload)

    plugin._vni_db.allocate_vni_for_router.assert_called_once_with(
        "context",
        "router-1",
        n_const.ATTR_NOT_SPECIFIED,
    )
    assert payload.latest_state[apidef.EVPN_VNI] == 500


def test_auto_mode_honors_supplied_vni(mocker):
    plugin = _make_plugin(
        mocker, _mode_metainfo(vrf.VNI_ALLOC_AUTO), allocate_return=42
    )
    payload = _create_payload(evpn_vni=42)

    plugin._process_router_create(None, None, None, payload)

    plugin._vni_db.allocate_vni_for_router.assert_called_once_with(
        "context", "router-1", 42
    )
    assert payload.latest_state[apidef.EVPN_VNI] == 42


def test_on_mode_allocates_only_supplied_vni(mocker):
    plugin = _make_plugin(mocker, _mode_metainfo(vrf.VNI_ALLOC_ON), allocate_return=77)
    payload = _create_payload(evpn_vni=77)

    plugin._process_router_create(None, None, None, payload)

    plugin._vni_db.allocate_vni_for_router.assert_called_once_with(
        "context", "router-1", 77
    )
    assert payload.latest_state[apidef.EVPN_VNI] == 77


def test_on_mode_does_not_auto_allocate(mocker):
    plugin = _make_plugin(mocker, _mode_metainfo(vrf.VNI_ALLOC_ON))
    payload = _create_payload()

    plugin._process_router_create(None, None, None, payload)

    plugin._vni_db.allocate_vni_for_router.assert_not_called()
    assert apidef.EVPN_VNI not in payload.latest_state


def test_off_mode_does_not_allocate(mocker):
    plugin = _make_plugin(mocker, _mode_metainfo(vrf.VNI_ALLOC_OFF))
    payload = _create_payload()

    plugin._process_router_create(None, None, None, payload)

    plugin._vni_db.allocate_vni_for_router.assert_not_called()
    assert apidef.EVPN_VNI not in payload.latest_state


def test_off_mode_rejects_explicit_vni(mocker):
    plugin = _make_plugin(mocker, _mode_metainfo(vrf.VNI_ALLOC_OFF))
    payload = _create_payload(evpn_vni=500)

    with pytest.raises(vrf.n_exc.BadRequest):
        plugin._process_router_create(None, None, None, payload)

    plugin._vni_db.allocate_vni_for_router.assert_not_called()


def test_missing_metainfo_defaults_to_off(mocker):
    # A flavor whose service profile carries no metainfo (e.g. Palo Alto) must
    # not get a VNI and must reject an explicit one -- this is the leak the
    # ATTR_NOT_SPECIFIED default plus off-by-default mode together close.
    plugin = _make_plugin(mocker, None)
    payload = _create_payload(evpn_vni=500)

    with pytest.raises(vrf.n_exc.BadRequest):
        plugin._process_router_create(None, None, None, payload)

    plugin._vni_db.allocate_vni_for_router.assert_not_called()


def test_router_without_flavor_defaults_to_off(mocker):
    plugin = _make_plugin(mocker, _mode_metainfo(vrf.VNI_ALLOC_AUTO))
    payload = _create_payload(flavor_id=n_const.ATTR_NOT_SPECIFIED)

    plugin._process_router_create(None, None, None, payload)

    plugin._vni_db.allocate_vni_for_router.assert_not_called()
    assert apidef.EVPN_VNI not in payload.latest_state


def test_invalid_mode_defaults_to_off(mocker):
    plugin = _make_plugin(mocker, _mode_metainfo("bogus"))
    payload = _create_payload()

    plugin._process_router_create(None, None, None, payload)

    plugin._vni_db.allocate_vni_for_router.assert_not_called()


def test_evpn_vni_default_is_attr_not_specified():
    # A bare ``router create`` (no evpn_vni) must leave the attribute as
    # ATTR_NOT_SPECIFIED, matching core neutron-lib. A ``0`` default would be
    # read by the core EVPNPlugin as an auto-allocate request and would
    # allocate a VNI on every router. See launchpad bug 2160992.
    attr = apidef.RESOURCE_ATTRIBUTE_MAP[apidef.COLLECTION_NAME][apidef.EVPN_VNI]
    assert attr["default"] is n_const.ATTR_NOT_SPECIFIED
