"""Scenario tests for baremetal (Ironic) port binding through the ML2 chain.

See neutron_understack/tests/scenarios/SCENARIOS.md for the catalog these tests
implement. Each test is tagged with its scenario ID via @pytest.mark.scenario.
"""

import pytest
from neutron.db import segments_db
from neutron.plugins.ml2 import db as ml2_db
from neutron_lib import constants as p_const
from neutron_lib.api.definitions import portbindings
from oslo_config import cfg

from neutron_understack.tests.scenarios.base import DEFAULT_PHYSNET
from neutron_understack.tests.scenarios.base import UnderstackMl2ScenarioBase

HOST = "host-1"


class TestBaremetalBinding(UnderstackMl2ScenarioBase):
    def _make_vxlan_network(self):
        return self._make_network(self.fmt, "vxlan-net", True)["network"]

    def _create_unbound_baremetal_port(self, net_id):
        res = self._create_port(
            self.fmt,
            net_id,
            arg_list=(portbindings.VNIC_TYPE,),
            is_admin=True,
            **{portbindings.VNIC_TYPE: portbindings.VNIC_BAREMETAL},
        )
        assert res.status_int == 201, res.body
        return self.deserialize(self.fmt, res)["port"]

    def _vif_attach(self, port_id, physnet=DEFAULT_PHYSNET, host=HOST):
        """Simulate the Ironic vif-attach: update the port with host + profile."""
        data = {
            "port": {
                portbindings.HOST_ID: host,
                portbindings.PROFILE: self.baremetal_binding_profile(physnet=physnet),
            }
        }
        # binding:host_id / binding:profile writes require the service role
        # under secure RBAC (this is the identity Ironic/Nova use).
        req = self.new_update_request("ports", data, port_id, as_service=True)
        res = req.get_response(self.api)
        assert res.status_int == 200, res.body
        return self.deserialize(self.fmt, res)["port"]

    @pytest.mark.scenario("BM-BIND-01")
    def test_baremetal_vif_attach_binds_hierarchically(self):
        net = self._make_vxlan_network()
        port = self._create_unbound_baremetal_port(net["id"])
        port_id = port["id"]
        # A freshly created baremetal port with no host is unbound.
        assert port[portbindings.VIF_TYPE] == portbindings.VIF_TYPE_UNBOUND

        updated = self._vif_attach(port_id)

        # undersync finalized the binding to VIF_TYPE_OTHER.
        assert updated[portbindings.VIF_TYPE] == portbindings.VIF_TYPE_OTHER

        # Two hierarchical binding levels: understack bound the VXLAN segment
        # (level 0, via continue_binding) and handed a dynamic VLAN segment to
        # undersync, which bound it (level 1, via set_binding).
        levels = ml2_db.get_binding_level_objs(self.context, port_id, HOST)
        assert len(levels) == 2, levels
        assert levels[0].driver == "understack"
        assert levels[1].driver == "undersync"

        # Top segment is VXLAN (the tenant network segment).
        top = segments_db.get_segment_by_id(self.context, levels[0].segment_id)
        assert top[segments_db.NETWORK_TYPE] == p_const.TYPE_VXLAN

        # Bottom segment is a *dynamically allocated* VLAN segment on our physnet.
        bottom = segments_db.get_segment_by_id(self.context, levels[1].segment_id)
        assert bottom[segments_db.NETWORK_TYPE] == p_const.TYPE_VLAN
        assert bottom[segments_db.PHYSICAL_NETWORK] == DEFAULT_PHYSNET

        # The switch reconcile fired for the port's VLAN group.
        self.undersync_mock.sync.assert_any_call(DEFAULT_PHYSNET)

    def _bottom_segment_id(self, port_id, host=HOST):
        levels = ml2_db.get_binding_level_objs(self.context, port_id, host)
        return levels[-1].segment_id

    @pytest.mark.scenario("BM-BIND-REUSE-01")
    def test_second_port_same_physnet_reuses_dynamic_segment(self):
        """A 2nd baremetal port on the same network+physnet reuses the VLAN seg."""
        net = self._make_vxlan_network()
        port_a = self._create_unbound_baremetal_port(net["id"])
        self._vif_attach(port_a["id"], host="host-a")
        port_b = self._create_unbound_baremetal_port(net["id"])
        self._vif_attach(port_b["id"], host="host-b")

        seg_a = self._bottom_segment_id(port_a["id"], "host-a")
        seg_b = self._bottom_segment_id(port_b["id"], "host-b")
        assert seg_a == seg_b, (seg_a, seg_b)

    @pytest.mark.scenario("PROV-BIND-01")
    def test_provisioning_network_port_binds(self):
        """A baremetal port on the provisioning network binds hierarchically."""
        net = self._make_vxlan_network()
        cfg.CONF.set_override("provisioning_network", net["id"], group="ml2_understack")
        port = self._create_unbound_baremetal_port(net["id"])

        updated = self._vif_attach(port["id"])

        assert updated[portbindings.VIF_TYPE] == portbindings.VIF_TYPE_OTHER
        self.undersync_mock.sync.assert_any_call(DEFAULT_PHYSNET)

    @pytest.mark.scenario("PROV-DEL-01")
    def test_provisioning_network_delete_retains_segment(self):
        """Deleting a provisioning-network port syncs but keeps the VLAN segment.

        The clean/provision cycle re-uses the segment, so unlike a tenant port
        (BM-BIND-05) the dynamic VLAN segment is not released on delete.
        """
        net = self._make_vxlan_network()
        cfg.CONF.set_override("provisioning_network", net["id"], group="ml2_understack")
        port = self._create_unbound_baremetal_port(net["id"])
        self._vif_attach(port["id"])
        vlan_segment_id = self._bottom_segment_id(port["id"])
        self.undersync_mock.reset_mock()

        self._delete("ports", port["id"], as_admin=True)

        # Sync fired, but the segment is retained (provisioning cycle).
        self.undersync_mock.sync.assert_any_call(DEFAULT_PHYSNET)
        assert segments_db.get_segment_by_id(self.context, vlan_segment_id) is not None

    @pytest.mark.scenario("BM-BIND-06")
    def test_vif_attach_without_ip_still_syncs(self):
        """A bound baremetal port with no IP still emits the physnet sync."""
        net = self._make_vxlan_network()
        # Subnet exists on the network, but the port is created with no IP.
        self._make_subnet(
            self.fmt, {"network": net}, gateway="10.8.0.1", cidr="10.8.0.0/24"
        )
        res = self._create_port(
            self.fmt,
            net["id"],
            arg_list=(portbindings.VNIC_TYPE,),
            is_admin=True,
            **{portbindings.VNIC_TYPE: portbindings.VNIC_BAREMETAL, "fixed_ips": []},
        )
        assert res.status_int == 201, res.body
        port = self.deserialize(self.fmt, res)["port"]
        assert port["fixed_ips"] == []

        updated = self._vif_attach(port["id"])

        assert updated[portbindings.VIF_TYPE] == portbindings.VIF_TYPE_OTHER
        self.undersync_mock.sync.assert_any_call(DEFAULT_PHYSNET)

    @pytest.mark.scenario("BM-BIND-02")
    def test_vif_attach_without_physical_network_refuses_binding(self):
        """A binding profile missing physical_network cannot be bound."""
        net = self._make_vxlan_network()
        port = self._create_unbound_baremetal_port(net["id"])

        # physnet=None omits physical_network from the profile.
        updated = self._vif_attach(port["id"], physnet=None)

        assert updated[portbindings.VIF_TYPE] == portbindings.VIF_TYPE_BINDING_FAILED
        assert ml2_db.get_binding_level_objs(self.context, port["id"], HOST) == []
        self.undersync_mock.sync.assert_not_called()

    @pytest.mark.scenario("BM-BIND-03")
    def test_unsupported_vnic_type_is_not_bound_by_us(self):
        """A non-baremetal/normal vnic_type is refused by our drivers."""
        net = self._make_vxlan_network()
        res = self._create_port(
            self.fmt,
            net["id"],
            arg_list=(portbindings.VNIC_TYPE,),
            is_admin=True,
            **{portbindings.VNIC_TYPE: portbindings.VNIC_DIRECT},
        )
        assert res.status_int == 201, res.body
        port = self.deserialize(self.fmt, res)["port"]

        updated = self._vif_attach(port["id"])

        assert updated[portbindings.VIF_TYPE] == portbindings.VIF_TYPE_BINDING_FAILED
        self.undersync_mock.sync.assert_not_called()

    # BUG rackerlabs/understack#2239: the dynamic VLAN segment leaks on
    # vif-detach -- see SCENARIOS.md "Known bugs". This test asserts the *desired*
    # behavior and currently fails. strict=True makes an unexpected pass fail the
    # run, prompting removal of the xfail once the driver is fixed.
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "understack#2239: dynamic VLAN segment leaks on vif-detach; "
            "_tenant_network_port_cleanup releases original_top_bound_segment "
            "(the non-dynamic VXLAN segment) instead of the dynamic VLAN segment"
        ),
    )
    @pytest.mark.scenario("BM-BIND-04")
    def test_vif_detach_releases_segment_and_reconciles(self):
        """Vif detach should unbind, reconcile the switch, AND release the VLAN.

        The bound->unbound transition must free the dynamic VLAN segment so its
        VLAN id is not leaked back to the pool. Today the driver reconciles
        (undersync.sync) but retains the segment (see the xfail reason).
        """
        net = self._make_vxlan_network()
        port = self._create_unbound_baremetal_port(net["id"])
        port_id = port["id"]
        self._vif_attach(port_id)

        levels = ml2_db.get_binding_level_objs(self.context, port_id, HOST)
        vlan_segment_id = levels[1].segment_id
        self.undersync_mock.reset_mock()

        # vif detach: clear host + profile.
        data = {"port": {portbindings.HOST_ID: "", portbindings.PROFILE: {}}}
        req = self.new_update_request("ports", data, port_id, as_service=True)
        res = req.get_response(self.api)
        assert res.status_int == 200, res.body
        updated = self.deserialize(self.fmt, res)["port"]

        assert updated[portbindings.VIF_TYPE] == portbindings.VIF_TYPE_UNBOUND
        # The switch is reconciled for the port's VLAN group ...
        self.undersync_mock.sync.assert_any_call(DEFAULT_PHYSNET)
        # ... and the dynamic VLAN segment is released (no port uses it anymore).
        assert segments_db.get_segment_by_id(self.context, vlan_segment_id) is None

    @pytest.mark.scenario("BM-BIND-05")
    def test_port_delete_releases_dynamic_vlan_segment(self):
        """Deleting a bound baremetal port releases its dynamic VLAN segment."""
        net = self._make_vxlan_network()
        port = self._create_unbound_baremetal_port(net["id"])
        port_id = port["id"]
        self._vif_attach(port_id)

        levels = ml2_db.get_binding_level_objs(self.context, port_id, HOST)
        vlan_segment_id = levels[1].segment_id
        assert segments_db.get_segment_by_id(self.context, vlan_segment_id) is not None
        self.undersync_mock.reset_mock()

        self._delete("ports", port_id, as_admin=True)

        # The dynamic VLAN segment is released now that no port uses it ...
        assert segments_db.get_segment_by_id(self.context, vlan_segment_id) is None
        # ... and the switch is reconciled for that VLAN group.
        self.undersync_mock.sync.assert_any_call(DEFAULT_PHYSNET)
