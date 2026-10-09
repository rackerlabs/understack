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
from neutron_lib.api.definitions import portbindings
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

    def _unbound_baremetal_port(self, net_id):
        res = self._create_port(
            self.fmt,
            net_id,
            arg_list=(portbindings.VNIC_TYPE,),
            is_admin=True,
            **{portbindings.VNIC_TYPE: portbindings.VNIC_BAREMETAL},
        )
        assert res.status_int == 201, res.body
        return self.deserialize(self.fmt, res)["port"]

    def _vif_attach(self, port_id, physnet=DEFAULT_PHYSNET, host="host-a"):
        data = {
            "port": {
                portbindings.HOST_ID: host,
                portbindings.PROFILE: self.baremetal_binding_profile(physnet=physnet),
            }
        }
        req = self.new_update_request("ports", data, port_id, as_service=True)
        with mock.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value=_FAKE_NN_TRUNK,
        ):
            res = req.get_response(self.api)
        assert res.status_int == 200, res.body
        return self.deserialize(self.fmt, res)["port"]

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

    @pytest.mark.scenario("TRUNK-ORDER-01")
    def test_subport_remove_deallocates_before_it_notifies_undersync(self):
        """Both drivers handle SUBPORTS AFTER_DELETE; order is by priority.

        The understack trunk driver deallocates the segment and the undersync
        driver notifies Undersync. Undersync computes the desired switch state
        when called, so it must run *after* the segment work -- guaranteed by
        undersync subscribing above the trunk driver's PRIORITY_DEFAULT. A
        recorder on each side pins the relative order, which the per-driver
        priority unit test cannot.
        """
        parent_net = self._make_network(self.fmt, "parent-net", True)["network"]["id"]
        parent_id = self._bind_baremetal_port(parent_net, DEFAULT_PHYSNET, "host-a")
        subport_net = self._make_network(self.fmt, "subport-net", True)["network"]["id"]
        subport_id = self._plain_port(subport_net)
        trunk_id = self._make_trunk(parent_id)
        self._add_subport(trunk_id, subport_id)
        self._assert_subport_bound(trunk_id, subport_id, "host-a")

        calls: list[str] = []
        trunk_driver = self.understack_driver.trunk_driver
        original_dealloc = trunk_driver._handle_segment_deallocation

        def _record_dealloc(*args, **kwargs):
            calls.append("understack.deallocate")
            return original_dealloc(*args, **kwargs)

        self.undersync_mock.sync.side_effect = lambda physnet: calls.append(
            f"undersync.sync:{physnet}"
        )

        with mock.patch.object(
            trunk_driver, "_handle_segment_deallocation", side_effect=_record_dealloc
        ):
            self._remove_subport(trunk_id, subport_id)

        assert calls == ["understack.deallocate", f"undersync.sync:{DEFAULT_PHYSNET}"]

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

    # The understack driver raises SubportSegmentationIDError in bind_port, but
    # ML2 has no way to abort a bind: it logs the failure and tries the next
    # mechanism driver, which binds the port. This asserts the desired behavior;
    # strict=True flips an unexpected pass into a failure, prompting removal of
    # the xfail once the upstream Neutron fix is backported.
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "native VLAN collision on parent bind is detected but ML2 cannot "
            "abort a bind; it falls through to the next mechanism driver and the "
            "port binds (vif_type=other). Needs the upstream Neutron fix backported"
        ),
    )
    @pytest.mark.scenario("TRUNK-PARENT-BIND-NATIVE-01")
    def test_unbound_trunk_rejects_native_vlan_collision_on_parent_bind(self):
        """Binding must revalidate subports once the native VLAN is known."""
        parent_net = self._make_network(self.fmt, "parent-net", True)["network"]["id"]
        parent = self._unbound_baremetal_port(parent_net)
        subport_net = self._make_network(self.fmt, "subport-net", True)["network"]["id"]
        subport_id = self._plain_port(subport_net)
        trunk_id = self._make_trunk(parent["id"])

        # This is valid while the parent is unbound because its native VLAN is
        # not known yet. Pin the segment that vif-attach will select so the
        # eventual collision is deterministic.
        self._add_subport(trunk_id, subport_id, seg_id=SUBPORT_VLAN)
        native_segment = {
            segments_db.NETWORK_TYPE: p_const.TYPE_VLAN,
            segments_db.PHYSICAL_NETWORK: DEFAULT_PHYSNET,
            segments_db.SEGMENTATION_ID: SUBPORT_VLAN,
        }
        segments_db.add_network_segment(
            self.context, parent_net, native_segment, is_dynamic=True
        )

        self.undersync_mock.reset_mock()
        updated = self._vif_attach(parent["id"])

        assert updated[portbindings.VIF_TYPE] == portbindings.VIF_TYPE_BINDING_FAILED
        assert not ml2_db.get_binding_level_objs(self.context, parent["id"], "host-a")
        assert not ml2_db.get_binding_level_objs(self.context, subport_id, "host-a")
        self.undersync_mock.sync.assert_not_called()

    @pytest.mark.scenario("TRUNK-PARENT-BIND-NATIVE-02")
    def test_unbound_trunk_with_subports_configures_on_parent_bind(self):
        """Everything created before the parent binds is configured at bind."""
        parent_net = self._make_network(self.fmt, "parent-net", True)["network"]["id"]
        parent = self._unbound_baremetal_port(parent_net)
        sub_net_a = self._make_network(self.fmt, "sub-a", True)["network"]["id"]
        sub_net_b = self._make_network(self.fmt, "sub-b", True)["network"]["id"]
        subport_a = self._plain_port(sub_net_a)
        subport_b = self._plain_port(sub_net_b)
        trunk_id = self._make_trunk(parent["id"])
        self._add_subport(trunk_id, subport_a, seg_id=1500)
        self._add_subport(trunk_id, subport_b, seg_id=1600)
        for net_id in (sub_net_a, sub_net_b):
            assert (
                segments_db.get_dynamic_segment(
                    self.context, net_id, physical_network=DEFAULT_PHYSNET
                )
                is None
            )

        self.undersync_mock.reset_mock()
        updated = self._vif_attach(parent["id"])

        assert updated[portbindings.VIF_TYPE] == portbindings.VIF_TYPE_OTHER
        self._assert_subport_bound(trunk_id, subport_a, "host-a", seg_id=1500)
        self._assert_subport_bound(trunk_id, subport_b, "host-a", seg_id=1600)
        self.undersync_mock.sync.assert_any_call(DEFAULT_PHYSNET)

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

    @pytest.mark.scenario("TRUNK-SEGID-NATIVE-01")
    def test_subport_segid_matching_native_vlan_rejected(self):
        parent_net = self._make_network(self.fmt, "parent-net", True)["network"]["id"]
        parent_id = self._bind_baremetal_port(parent_net, DEFAULT_PHYSNET, "host-a")
        subport_net = self._make_network(self.fmt, "subport-net", True)["network"]["id"]
        subport_id = self._plain_port(subport_net)
        trunk_id = self._make_trunk(parent_id)
        native_segment = segments_db.get_dynamic_segment(
            self.context, parent_net, physical_network=DEFAULT_PHYSNET
        )

        # subports_added raises SubportSegmentationIDError when the requested
        # tag is the native VLAN, and the callback machinery wraps it.
        with pytest.raises(cb_exc.CallbackFailure) as exc_info:
            self._add_subport(
                trunk_id,
                subport_id,
                seg_id=native_segment[segments_db.SEGMENTATION_ID],
            )
        assert "matches the native VLAN" in str(exc_info.value)
        assert not ml2_db.get_binding_level_objs(self.context, subport_id, "host-a")
        assert (
            segments_db.get_dynamic_segment(
                self.context, subport_net, physical_network=DEFAULT_PHYSNET
            )
            is None
        )

    @pytest.mark.scenario("TRUNK-SEGID-RANGE-01")
    def test_subport_segid_outside_configured_range_is_rejected(self):
        parent_net = self._make_network(self.fmt, "parent-net", True)["network"]["id"]
        parent_id = self._bind_baremetal_port(parent_net, DEFAULT_PHYSNET, "host-a")
        subport_net = self._make_network(self.fmt, "subport-net", True)["network"]["id"]
        subport_id = self._plain_port(subport_net)
        trunk_id = self._make_trunk(parent_id)
        with pytest.raises(cb_exc.CallbackFailure) as exc_info:
            self._add_subport(trunk_id, subport_id, seg_id=4000)
        assert "outside the configured tenant trunk VLAN range 2-3871" in str(
            exc_info.value
        )
        assert not ml2_db.get_binding_level_objs(self.context, subport_id, "host-a")
        assert (
            segments_db.get_dynamic_segment(
                self.context, subport_net, physical_network=DEFAULT_PHYSNET
            )
            is None
        )
