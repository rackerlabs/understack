"""Scenario tests for trunk subport operations driving undersync sync.

See neutron_understack/tests/scenarios/SCENARIOS.md (TRUNK-*) for the catalog.
"""

import uuid
from unittest import mock

import pytest
from neutron.db import segments_db
from neutron.objects.network import NetworkSegment
from neutron.plugins.ml2 import db as ml2_db
from neutron.services.trunk import exceptions as trunk_exc
from neutron_lib import constants as p_const
from neutron_lib.callbacks import exceptions as cb_exc

from neutron_understack.tests.scenarios.base import DEFAULT_PHYSNET
from neutron_understack.tests.scenarios.base import UnderstackMl2TrunkScenarioBase

# Any VLAN in the default tenant range [1, 3799]; no NetworkSegmentRange rows
# exist in the harness, so the whole range is allowed for subports.
SUBPORT_VLAN = 1500

# fetch_network_node_trunk_id() does live OVN gateway + Ironic discovery; stub it
# to a non-matching id so the tenant-trunk segmentation check runs normally.
_FAKE_NN_TRUNK = str(uuid.uuid4())


class TestTrunkOperations(UnderstackMl2TrunkScenarioBase):
    def _plain_port(self, net_id):
        res = self._create_port(self.fmt, net_id, is_admin=True)
        assert res.status_int == 201, res.body
        return self.deserialize(self.fmt, res)["port"]["id"]

    def _make_trunk(self, parent_id):
        trunk = self.trunk_plugin.create_trunk(
            self.context,
            {
                "trunk": {
                    "port_id": parent_id,
                    "project_id": self._project_id,
                    "admin_state_up": True,
                    "sub_ports": [],
                }
            },
        )
        return trunk["id"]

    def _add_subport(self, trunk_id, subport_id, seg_id=SUBPORT_VLAN):
        with mock.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value=_FAKE_NN_TRUNK,
        ):
            self.trunk_plugin.add_subports(
                self.context,
                trunk_id,
                {
                    "sub_ports": [
                        {
                            "port_id": subport_id,
                            "segmentation_type": "vlan",
                            "segmentation_id": seg_id,
                        }
                    ]
                },
            )

    def _remove_subport(self, trunk_id, subport_id):
        with mock.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value=_FAKE_NN_TRUNK,
        ):
            return self.trunk_plugin.remove_subports(
                self.context, trunk_id, {"sub_ports": [{"port_id": subport_id}]}
            )

    def _trunk_subports(self, trunk_id):
        return self.trunk_plugin.get_trunk(self.context, trunk_id)["sub_ports"]

    def _assert_subport_bound(self, trunk_id, subport_id, host, seg_id=SUBPORT_VLAN):
        assert {
            subport["port_id"]: subport for subport in self._trunk_subports(trunk_id)
        }[subport_id] == {
            "port_id": subport_id,
            "segmentation_type": "vlan",
            "segmentation_id": seg_id,
        }

        levels = ml2_db.get_binding_level_objs(self.context, subport_id, host)
        assert len(levels) == 1, levels
        assert levels[0].driver == "understack"
        assert levels[0].level == 0

        segment = segments_db.get_segment_by_id(self.context, levels[0].segment_id)
        assert segment[segments_db.NETWORK_TYPE] == p_const.TYPE_VLAN
        assert segment[segments_db.PHYSICAL_NETWORK] == DEFAULT_PHYSNET
        segment_obj = NetworkSegment.get_object(self.context, id=levels[0].segment_id)
        assert segment_obj.is_dynamic
        return levels[0].segment_id

    def _assert_subport_unbound(self, subport_id, host, segment_id):
        assert not ml2_db.get_binding_level_objs(self.context, subport_id, host)
        assert segments_db.get_segment_by_id(self.context, segment_id) is None

    @pytest.mark.scenario("TRUNK-SUB-ADD")
    def test_subport_add_syncs_parent_physnet(self):
        parent_net = self._make_network(self.fmt, "parent-net", True)["network"]["id"]
        parent_id = self._bind_baremetal_port(parent_net, DEFAULT_PHYSNET, "host-a")
        subport_net = self._make_network(self.fmt, "subport-net", True)["network"]["id"]
        subport_id = self._plain_port(subport_net)
        trunk_id = self._make_trunk(parent_id)

        self.undersync_mock.reset_mock()
        self._add_subport(trunk_id, subport_id)

        self._assert_subport_bound(trunk_id, subport_id, "host-a")
        self.undersync_mock.sync.assert_any_call(DEFAULT_PHYSNET)

    @pytest.mark.scenario("TRUNK-SUB-DEL")
    def test_subport_remove_syncs_parent_physnet(self):
        parent_net = self._make_network(self.fmt, "parent-net", True)["network"]["id"]
        parent_id = self._bind_baremetal_port(parent_net, DEFAULT_PHYSNET, "host-a")
        subport_net = self._make_network(self.fmt, "subport-net", True)["network"]["id"]
        subport_id = self._plain_port(subport_net)
        trunk_id = self._make_trunk(parent_id)
        self._add_subport(trunk_id, subport_id)
        segment_id = self._assert_subport_bound(trunk_id, subport_id, "host-a")

        self.undersync_mock.reset_mock()
        updated_trunk = self._remove_subport(trunk_id, subport_id)

        assert updated_trunk["sub_ports"] == []
        self._assert_subport_unbound(subport_id, "host-a", segment_id)
        self.undersync_mock.sync.assert_any_call(DEFAULT_PHYSNET)

    @pytest.mark.scenario("TRUNK-PARENT-NOIP")
    def test_subport_add_syncs_when_parent_has_no_ip(self):
        # Parent network has a subnet, but the parent port is bound with no IP.
        parent_net = self._make_network(self.fmt, "parent-net", True)
        self._make_subnet(self.fmt, parent_net, gateway="10.9.0.1", cidr="10.9.0.0/24")
        parent_id = self._bind_baremetal_port(
            parent_net["network"]["id"], DEFAULT_PHYSNET, "host-a", fixed_ips=[]
        )
        subport_net = self._make_network(self.fmt, "subport-net", True)["network"]["id"]
        subport_id = self._plain_port(subport_net)
        trunk_id = self._make_trunk(parent_id)

        self.undersync_mock.reset_mock()
        self._add_subport(trunk_id, subport_id)

        self._assert_subport_bound(trunk_id, subport_id, "host-a")
        self.undersync_mock.sync.assert_any_call(DEFAULT_PHYSNET)

    @pytest.mark.scenario("TRUNK-DEL-01")
    def test_trunk_delete_syncs_parent_physnet(self):
        parent_net = self._make_network(self.fmt, "parent-net", True)["network"]["id"]
        parent_id = self._bind_baremetal_port(parent_net, DEFAULT_PHYSNET, "host-a")
        subport_net = self._make_network(self.fmt, "subport-net", True)["network"]["id"]
        subport_id = self._plain_port(subport_net)
        trunk_id = self._make_trunk(parent_id)
        self._add_subport(trunk_id, subport_id)
        segment_id = self._assert_subport_bound(trunk_id, subport_id, "host-a")

        self.undersync_mock.reset_mock()
        with mock.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value=_FAKE_NN_TRUNK,
        ):
            self.trunk_plugin.delete_trunk(self.context, trunk_id)

        with pytest.raises(trunk_exc.TrunkNotFound):
            self.trunk_plugin.get_trunk(self.context, trunk_id)
        self._assert_subport_unbound(subport_id, "host-a", segment_id)
        self.undersync_mock.sync.assert_any_call(DEFAULT_PHYSNET)

    @pytest.mark.scenario("TRUNK-PARENT-UNBOUND-01")
    def test_subport_add_unbound_parent_no_sync(self):
        # An unbound (plain) parent port: no switchport config, no sync.
        parent_net = self._make_network(self.fmt, "parent-net", True)["network"]["id"]
        parent_id = self._plain_port(parent_net)
        subport_net = self._make_network(self.fmt, "subport-net", True)["network"]["id"]
        subport_id = self._plain_port(subport_net)
        trunk_id = self._make_trunk(parent_id)

        self.undersync_mock.reset_mock()
        self._add_subport(trunk_id, subport_id)

        assert self._trunk_subports(trunk_id)[0]["port_id"] == subport_id
        assert not ml2_db.get_binding_level_objs(self.context, subport_id, "")
        assert (
            segments_db.get_dynamic_segment(
                self.context, subport_net, physical_network=DEFAULT_PHYSNET
            )
            is None
        )
        self.undersync_mock.sync.assert_not_called()

    @pytest.mark.scenario("TRUNK-MULTI-01")
    def test_multiple_subports_add_syncs(self):
        parent_net = self._make_network(self.fmt, "parent-net", True)["network"]["id"]
        parent_id = self._bind_baremetal_port(parent_net, DEFAULT_PHYSNET, "host-a")
        sub_net_a = self._make_network(self.fmt, "sub-a", True)["network"]["id"]
        sub_net_b = self._make_network(self.fmt, "sub-b", True)["network"]["id"]
        subport_a = self._plain_port(sub_net_a)
        subport_b = self._plain_port(sub_net_b)
        trunk_id = self._make_trunk(parent_id)

        self.undersync_mock.reset_mock()
        with mock.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value=_FAKE_NN_TRUNK,
        ):
            self.trunk_plugin.add_subports(
                self.context,
                trunk_id,
                {
                    "sub_ports": [
                        {
                            "port_id": subport_a,
                            "segmentation_type": "vlan",
                            "segmentation_id": 1500,
                        },
                        {
                            "port_id": subport_b,
                            "segmentation_type": "vlan",
                            "segmentation_id": 1600,
                        },
                    ]
                },
            )

        self._assert_subport_bound(trunk_id, subport_a, "host-a", seg_id=1500)
        segment_b = self._assert_subport_bound(
            trunk_id, subport_b, "host-a", seg_id=1600
        )
        segment_a = ml2_db.get_binding_level_objs(self.context, subport_a, "host-a")[
            0
        ].segment_id
        assert segment_a != segment_b
        self.undersync_mock.sync.assert_any_call(DEFAULT_PHYSNET)

    @pytest.mark.scenario("TRUNK-SEGID-RANGE-01")
    def test_subport_segid_out_of_range_rejected(self):
        parent_net = self._make_network(self.fmt, "parent-net", True)["network"]["id"]
        parent_id = self._bind_baremetal_port(parent_net, DEFAULT_PHYSNET, "host-a")
        subport_net = self._make_network(self.fmt, "subport-net", True)["network"]["id"]
        subport_id = self._plain_port(subport_net)
        trunk_id = self._make_trunk(parent_id)

        # 4000 is a valid VLAN but outside the default tenant range [1, 3799].
        # subports_added raises SubportSegmentationIDError, which the SUBPORTS
        # PRECOMMIT_CREATE callback machinery re-raises as CallbackFailure.
        with pytest.raises(cb_exc.CallbackFailure) as exc_info:
            self._add_subport(trunk_id, subport_id, seg_id=4000)
        assert "Segmentation ID" in str(exc_info.value)
        assert not ml2_db.get_binding_level_objs(self.context, subport_id, "host-a")
        assert (
            segments_db.get_dynamic_segment(
                self.context, subport_net, physical_network=DEFAULT_PHYSNET
            )
            is None
        )
