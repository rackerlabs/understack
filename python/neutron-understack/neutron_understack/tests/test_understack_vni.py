from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from neutron_understack.api.definitions import understack_vni as apidef
from neutron_understack.l3_router import understack_vni_db
from neutron_understack.l3_router import vrf


class FakeFlavorPlugin:
    def __init__(self, driver):
        self.driver = driver

    def get_flavor(self, _context, flavor_id):
        return {"id": flavor_id}

    def get_flavor_next_provider(self, _context, _flavor_id):
        return [{"driver": self.driver}]


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


def test_vrf_router_create_allocates_vni(mocker):
    mocker.patch.object(
        vrf.directory,
        "get_plugin",
        return_value=FakeFlavorPlugin(vrf._vrf_provider_driver()),
    )
    plugin = vrf.UnderstackVniPlugin.__new__(vrf.UnderstackVniPlugin)
    plugin._vni_db = mocker.Mock()
    plugin._vni_db.allocate_vni_for_router.return_value = 500
    payload = SimpleNamespace(
        context="context",
        resource_id="router-1",
        latest_state={
            "id": "router-1",
            "flavor_id": "flavor-1",
            apidef.EVPN_VNI: 0,
        },
    )

    plugin._process_router_create(None, None, None, payload)

    plugin._vni_db.allocate_vni_for_router.assert_called_once_with(
        "context",
        "router-1",
        0,
    )
    assert payload.latest_state[apidef.EVPN_VNI] == 500


def test_non_vrf_router_create_rejects_explicit_vni(mocker):
    mocker.patch.object(
        vrf.directory,
        "get_plugin",
        return_value=FakeFlavorPlugin("neutron_understack.l3_router.svi.Svi"),
    )
    plugin = vrf.UnderstackVniPlugin.__new__(vrf.UnderstackVniPlugin)
    plugin._vni_db = mocker.Mock()
    payload = SimpleNamespace(
        context="context",
        resource_id="router-1",
        latest_state={
            "id": "router-1",
            "flavor_id": "flavor-1",
            apidef.EVPN_VNI: 500,
        },
    )

    with pytest.raises(vrf.n_exc.BadRequest):
        plugin._process_router_create(None, None, None, payload)

    plugin._vni_db.allocate_vni_for_router.assert_not_called()
