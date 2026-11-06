"""Scenario tests for the understack_fabric_vlan ML2 extension driver.

See neutron_understack/tests/scenarios/SCENARIOS.md (SVLAN-*) for the catalog.
"""

import uuid
from unittest import mock

import pytest
from neutron.db import segments_db
from neutron.objects.network_segment_range import NetworkSegmentRange
from neutron.plugins.ml2 import db as ml2_db
from neutron_lib import constants as p_const
from neutron_lib.api.definitions import portbindings
from neutron_lib.api.definitions import provider_net as pnet
from neutron_lib.callbacks import exceptions as cb_exc
from oslo_config import cfg

from neutron_understack.tests.scenarios.base import DEFAULT_PHYSNET
from neutron_understack.tests.scenarios.base import SECOND_PHYSNET
from neutron_understack.tests.scenarios.base import UnderstackMl2ScenarioBase
from neutron_understack.tests.scenarios.base import UnderstackMl2TrunkScenarioBase

# The default [ml2_understack] fabric_vlan_physical_network.
FABRIC_PHYSNET = "understack_fabric_vlan"
FABRIC_MIN = 3000
FABRIC_MAX = 3010
FABRIC_VLAN = 3005

_FAKE_NN_TRUNK = str(uuid.uuid4())


class _FabricVlanMixin:
    def setUp(self):
        cfg.CONF.set_override(
            "extension_drivers", ["understack_fabric_vlan"], group="ml2"
        )
        super().setUp()
        # Created after plugin init, so these tests exercise the first-use
        # lookup. Shared, so allowed_tenant_vlan_id_ranges() excludes it.
        NetworkSegmentRange(
            self.context,
            name="fabric-vlans",
            default=False,
            shared=True,
            network_type=p_const.TYPE_VLAN,
            physical_network=FABRIC_PHYSNET,
            minimum=FABRIC_MIN,
            maximum=FABRIC_MAX,
        ).create()

    def _create_fabric_network(
        self, fabric_vlan=FABRIC_VLAN, name="fabric-net", as_admin=True
    ):
        kwargs = {} if fabric_vlan is None else {"fabric_vlan": fabric_vlan}
        return self._create_network(
            self.fmt,
            name,
            True,
            arg_list=("fabric_vlan",),
            as_admin=as_admin,
            **kwargs,
        )

    def _make_fabric_network(self, fabric_vlan=FABRIC_VLAN, name="fabric-net"):
        res = self._create_fabric_network(fabric_vlan, name)
        assert res.status_int == 201, res.body
        return self.deserialize(self.fmt, res)["network"]

    def _create_provider_vlan_network(self, physnet, vlan, **kwargs):
        return self._create_network(
            self.fmt,
            "provider-vlan",
            True,
            arg_list=(
                pnet.NETWORK_TYPE,
                pnet.PHYSICAL_NETWORK,
                pnet.SEGMENTATION_ID,
                "fabric_vlan",
            ),
            as_admin=True,
            **{
                pnet.NETWORK_TYPE: p_const.TYPE_VLAN,
                pnet.PHYSICAL_NETWORK: physnet,
                pnet.SEGMENTATION_ID: vlan,
            },
            **kwargs,
        )

    def _bottom_segment(self, port_id, host):
        levels = ml2_db.get_binding_level_objs(self.context, port_id, host)
        assert len(levels) == 2, levels
        return segments_db.get_segment_by_id(self.context, levels[1].segment_id)


class TestFabricVlanNetwork(_FabricVlanMixin, UnderstackMl2ScenarioBase):
    @pytest.mark.scenario("SVLAN-01")
    def test_vxlan_network_reserves_its_fabric_vlan(self):
        net = self._make_fabric_network()
        assert net["fabric_vlan"] == FABRIC_VLAN
        shown = self._show("networks", net["id"], as_admin=True)["network"]
        assert shown["fabric_vlan"] == FABRIC_VLAN

    @pytest.mark.scenario("SVLAN-01")
    def test_project_member_can_create_a_fabric_vlan_network(self):
        res = self._create_fabric_network(as_admin=False)
        assert res.status_int == 201, res.body
        net = self.deserialize(self.fmt, res)["network"]
        assert net["fabric_vlan"] == FABRIC_VLAN
        shown = self._show("networks", net["id"])["network"]
        assert shown["fabric_vlan"] == FABRIC_VLAN

    @pytest.mark.scenario("SVLAN-02")
    def test_vxlan_network_without_fabric_vlan_is_allowed(self):
        res = self._create_fabric_network(fabric_vlan=None)
        assert res.status_int == 201, res.body
        net = self.deserialize(self.fmt, res)["network"]
        assert net["fabric_vlan"] is None
        shown = self._show("networks", net["id"], as_admin=True)["network"]
        assert shown["fabric_vlan"] is None

    @pytest.mark.scenario("SVLAN-03")
    def test_fabric_vlan_outside_the_range_is_rejected(self):
        res = self._create_fabric_network(fabric_vlan=FABRIC_MAX + 1)
        assert res.status_int == 400, res.body

    @pytest.mark.scenario("SVLAN-03")
    def test_non_vxlan_network_needs_no_fabric_vlan(self):
        res = self._create_provider_vlan_network(DEFAULT_PHYSNET, 10)
        assert res.status_int == 201, res.body
        assert self.deserialize(self.fmt, res)["network"]["fabric_vlan"] is None

    @pytest.mark.scenario("SVLAN-03")
    def test_non_vxlan_network_rejects_fabric_vlan(self):
        res = self._create_provider_vlan_network(
            DEFAULT_PHYSNET, 10, fabric_vlan=FABRIC_VLAN
        )
        assert res.status_int == 400, res.body

    @pytest.mark.scenario("SVLAN-04")
    def test_fabric_vlan_is_unique_until_its_network_is_deleted(self):
        net = self._make_fabric_network()

        res = self._create_fabric_network(name="other-net")
        assert res.status_int == 409, res.body

        self._delete("networks", net["id"], as_admin=True)
        assert self._make_fabric_network(name="other-net")["fabric_vlan"] == (
            FABRIC_VLAN
        )

    def _update_fabric_vlan(self, net_id, fabric_vlan):
        req = self.new_update_request(
            "networks",
            {"network": {"fabric_vlan": fabric_vlan}},
            net_id,
            as_admin=True,
        )
        return req.get_response(self.api)

    @pytest.mark.scenario("SVLAN-05")
    def test_network_can_gain_a_fabric_vlan(self):
        net = self._make_fabric_network(fabric_vlan=None)

        res = self._update_fabric_vlan(net["id"], FABRIC_VLAN)

        assert res.status_int == 200, res.body
        assert self.deserialize(self.fmt, res)["network"]["fabric_vlan"] == (
            FABRIC_VLAN
        )
        shown = self._show("networks", net["id"], as_admin=True)["network"]
        assert shown["fabric_vlan"] == FABRIC_VLAN

    @pytest.mark.scenario("SVLAN-05")
    def test_gaining_a_held_or_out_of_range_fabric_vlan_is_rejected(self):
        self._make_fabric_network(name="holder")
        net = self._make_fabric_network(fabric_vlan=None)

        assert self._update_fabric_vlan(net["id"], FABRIC_VLAN).status_int == 409
        assert self._update_fabric_vlan(net["id"], FABRIC_MAX + 1).status_int == 400

    @pytest.mark.scenario("SVLAN-05")
    def test_fabric_vlan_cannot_be_changed_or_cleared(self):
        net = self._make_fabric_network()

        assert self._update_fabric_vlan(net["id"], FABRIC_VLAN).status_int == 200
        assert self._update_fabric_vlan(net["id"], FABRIC_VLAN + 1).status_int == 400
        assert self._update_fabric_vlan(net["id"], None).status_int == 400

    @pytest.mark.scenario("SVLAN-06")
    def test_binding_uses_the_fabric_vlan_on_every_physnet(self):
        net = self._make_fabric_network()

        port_a = self._bind_baremetal_port(net["id"], DEFAULT_PHYSNET, "host-a")
        port_b = self._bind_baremetal_port(net["id"], SECOND_PHYSNET, "host-b")

        for port_id, host, physnet in (
            (port_a, "host-a", DEFAULT_PHYSNET),
            (port_b, "host-b", SECOND_PHYSNET),
        ):
            bottom = self._bottom_segment(port_id, host)
            assert bottom[segments_db.PHYSICAL_NETWORK] == physnet
            assert bottom[segments_db.SEGMENTATION_ID] == FABRIC_VLAN

    @pytest.mark.scenario("SVLAN-06")
    def test_binding_uses_a_fabric_vlan_gained_after_creation(self):
        net = self._make_fabric_network(fabric_vlan=None)
        assert self._update_fabric_vlan(net["id"], FABRIC_VLAN).status_int == 200

        port_id = self._bind_baremetal_port(net["id"], DEFAULT_PHYSNET, "host-a")

        bottom = self._bottom_segment(port_id, "host-a")
        assert bottom[segments_db.SEGMENTATION_ID] == FABRIC_VLAN

    @pytest.mark.scenario("SVLAN-07")
    def test_binding_fails_when_the_physnet_already_has_the_vlan(self):
        res = self._create_provider_vlan_network(DEFAULT_PHYSNET, FABRIC_VLAN)
        assert res.status_int == 201, res.body
        net = self._make_fabric_network()

        port_id = self._bind_baremetal_port(net["id"], DEFAULT_PHYSNET, "host-a")

        port = self._show("ports", port_id, as_admin=True)["port"]
        assert port[portbindings.VIF_TYPE] == portbindings.VIF_TYPE_BINDING_FAILED
        assert not ml2_db.get_binding_level_objs(self.context, port_id, "host-a")


class TestFabricVlanDisabled(UnderstackMl2ScenarioBase):
    @pytest.mark.scenario("SVLAN-08")
    def test_attribute_is_absent(self):
        net = self._make_network(self.fmt, "vxlan-net", True)["network"]
        assert "fabric_vlan" not in net


class TestFabricVlanTrunk(_FabricVlanMixin, UnderstackMl2TrunkScenarioBase):
    def _plain_port(self, net_id):
        res = self._create_port(self.fmt, net_id, is_admin=True)
        assert res.status_int == 201, res.body
        return self.deserialize(self.fmt, res)["port"]["id"]

    def _add_subport(self, parent_id, subport_id, seg_id):
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
        with mock.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value=_FAKE_NN_TRUNK,
        ):
            self.trunk_plugin.add_subports(
                self.context,
                trunk["id"],
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

    @pytest.mark.scenario("SVLAN-09")
    def test_subport_tagged_with_its_fabric_vlan_is_allowed(self):
        parent_net = self._make_fabric_network(fabric_vlan=FABRIC_MIN, name="parent")
        parent_id = self._bind_baremetal_port(parent_net["id"], DEFAULT_PHYSNET, "h")
        sub_net = self._make_fabric_network(name="sub")
        subport_id = self._plain_port(sub_net["id"])

        self._add_subport(parent_id, subport_id, FABRIC_VLAN)

        levels = ml2_db.get_binding_level_objs(self.context, subport_id, "h")
        assert len(levels) == 1, levels
        segment = segments_db.get_segment_by_id(self.context, levels[0].segment_id)
        assert segment[segments_db.PHYSICAL_NETWORK] == DEFAULT_PHYSNET
        assert segment[segments_db.SEGMENTATION_ID] == FABRIC_VLAN

    @pytest.mark.scenario("SVLAN-09")
    def test_subport_tagged_with_another_fabric_vlan_is_rejected(self):
        parent_net = self._make_fabric_network(fabric_vlan=FABRIC_MIN, name="parent")
        parent_id = self._bind_baremetal_port(parent_net["id"], DEFAULT_PHYSNET, "h")
        sub_net = self._make_fabric_network(name="sub")
        subport_id = self._plain_port(sub_net["id"])

        with pytest.raises(cb_exc.CallbackFailure):
            self._add_subport(parent_id, subport_id, FABRIC_VLAN + 1)
