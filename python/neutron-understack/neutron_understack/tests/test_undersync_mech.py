from unittest.mock import MagicMock

import pytest
from neutron_lib import constants as p_const
from neutron_lib.api.definitions import portbindings
from neutron_lib.plugins.ml2 import api

from neutron_understack.undersync_mech import UndersyncDriver


@pytest.fixture
def driver():
    d = UndersyncDriver()
    d.initialize()
    return d


def _make_context(vnic_type=portbindings.VNIC_BAREMETAL, segments=None):
    context = MagicMock()
    context.current = {"id": "port-1", portbindings.VNIC_TYPE: vnic_type}
    context.segments_to_bind = segments or []
    return context


@pytest.fixture
def vlan_segment():
    def _make(segment_id="seg-vlan-1"):
        return {
            api.ID: segment_id,
            api.NETWORK_TYPE: p_const.TYPE_VLAN,
            api.SEGMENTATION_ID: 100,
            api.PHYSICAL_NETWORK: "physnet1",
            api.MTU: 1500,
        }

    return _make


@pytest.fixture
def vxlan_segment():
    def _make(segment_id="seg-vxlan-1"):
        return {
            api.ID: segment_id,
            api.NETWORK_TYPE: p_const.TYPE_VXLAN,
            api.SEGMENTATION_ID: 1000,
            api.PHYSICAL_NETWORK: None,
            api.MTU: 1450,
        }

    return _make


class TestUndersyncDriverBindPort:
    def test_binds_vlan_segment(self, driver, vlan_segment):
        seg = vlan_segment()
        ctx = _make_context(segments=[seg])

        driver.bind_port(ctx)

        ctx.set_binding.assert_called_once_with(
            segment_id=seg[api.ID],
            vif_type=portbindings.VIF_TYPE_OTHER,
            vif_details={},
            status=p_const.PORT_STATUS_ACTIVE,
        )

    def test_binds_first_vlan_segment_only(self, driver, vlan_segment):
        seg1 = vlan_segment("seg-vlan-1")
        seg2 = vlan_segment("seg-vlan-2")
        ctx = _make_context(segments=[seg1, seg2])

        driver.bind_port(ctx)

        ctx.set_binding.assert_called_once_with(
            segment_id=seg1[api.ID],
            vif_type=portbindings.VIF_TYPE_OTHER,
            vif_details={},
            status=p_const.PORT_STATUS_ACTIVE,
        )

    def test_skips_vxlan_segment(self, driver, vxlan_segment):
        ctx = _make_context(segments=[vxlan_segment()])

        driver.bind_port(ctx)

        ctx.set_binding.assert_not_called()

    def test_skips_unsupported_vnic_type(self, driver, vlan_segment):
        ctx = _make_context(vnic_type="direct", segments=[vlan_segment()])

        driver.bind_port(ctx)

        ctx.set_binding.assert_not_called()

    def test_normal_vnic_type_is_not_supported(self, driver, vlan_segment):
        ctx = _make_context(
            vnic_type=portbindings.VNIC_NORMAL, segments=[vlan_segment()]
        )

        driver.bind_port(ctx)

        ctx.set_binding.assert_not_called()

    def test_binds_vlan_when_preceded_by_vxlan(
        self, driver, vxlan_segment, vlan_segment
    ):
        vlan = vlan_segment()
        ctx = _make_context(segments=[vxlan_segment(), vlan])

        driver.bind_port(ctx)

        ctx.set_binding.assert_called_once_with(
            segment_id=vlan[api.ID],
            vif_type=portbindings.VIF_TYPE_OTHER,
            vif_details={},
            status=p_const.PORT_STATUS_ACTIVE,
        )

    def test_empty_segments_to_bind(self, driver):
        ctx = _make_context(segments=[])

        driver.bind_port(ctx)

        ctx.set_binding.assert_not_called()

    def test_skips_direct_vnic_type(self, driver, vlan_segment):
        ctx = _make_context(
            vnic_type=portbindings.VNIC_DIRECT, segments=[vlan_segment()]
        )

        driver.bind_port(ctx)

        ctx.set_binding.assert_not_called()

    def test_logs_warning_when_no_vlan_segment_found(
        self, driver, vxlan_segment, caplog
    ):
        ctx = _make_context(segments=[vxlan_segment()])

        driver.bind_port(ctx)

        assert "no VLAN segment found" in caplog.text
        ctx.set_binding.assert_not_called()
