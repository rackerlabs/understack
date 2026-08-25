"""Scenario tests for VRF router interface attach vs. bound baremetal ports.

See neutron_understack/tests/scenarios/SCENARIOS.md (VRF-ROUTER-*) for the catalog.
"""

from unittest import mock

import pytest

from neutron_understack.tests.scenarios.base import DEFAULT_PHYSNET
from neutron_understack.tests.scenarios.base import SECOND_PHYSNET
from neutron_understack.tests.scenarios.base import UnderstackMl2RouterScenarioBase


class TestVrfRouterInterface(UnderstackMl2RouterScenarioBase):
    # BUG: attaching a VRF router interface to a network does not reconcile the
    # switches carrying that network's already-bound baremetal ports -- undersync
    # is never asked to sync those physnets. This test asserts the desired
    # behavior and currently fails; strict=True flips it to a failure (prompting
    # removal of the xfail) once the driver syncs on router attach.
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "understack#2240: VRF router interface attach does not sync the "
            "physnets of baremetal ports already bound on the network"
        ),
    )
    @pytest.mark.scenario("VRF-ROUTER-ATTACH-01")
    def test_vrf_router_interface_syncs_bound_port_physnets(self):
        net = self._make_network(self.fmt, "vxlan-net", True)
        net_id = net["network"]["id"]
        subnet = self._make_subnet(
            self.fmt, net, gateway="10.0.0.1", cidr="10.0.0.0/24"
        )["subnet"]

        # Two baremetal ports on this network, bound to different physnets.
        self._bind_baremetal_port(net_id, DEFAULT_PHYSNET, "host-a")
        self._bind_baremetal_port(net_id, SECOND_PHYSNET, "host-b")

        # Isolate the router attach from the sync calls made during the binds.
        self.undersync_mock.reset_mock()

        # Create a VRF (flavored) router and attach the subnet on the internal
        # side. The flavored path is simulated by patching _router_has_flavor,
        # mirroring test_routers.py; this is the branch a real VRF router takes.
        with mock.patch(
            "neutron_understack.routers._router_has_flavor", return_value=True
        ):
            router = self._create_router()
            self.l3_plugin.add_router_interface(
                self.context, router["id"], {"subnet_id": subnet["id"]}
            )

        # Desired: the switches carrying the network's baremetal ports get
        # reconciled, so undersync syncs each of their physnets.
        synced = {
            call.args[0]
            for call in self.undersync_mock.sync.call_args_list
            if call.args
        }
        assert DEFAULT_PHYSNET in synced
        assert SECOND_PHYSNET in synced

    # BUG: the teardown counterpart of the attach gap -- detaching a VRF router
    # interface also fails to sync the network's bound baremetal physnets.
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "understack#2240: VRF router interface detach does not sync the "
            "physnets of baremetal ports still bound on the network"
        ),
    )
    @pytest.mark.scenario("VRF-ROUTER-DETACH-01")
    def test_vrf_router_interface_detach_syncs_bound_port_physnets(self):
        net = self._make_network(self.fmt, "vxlan-net", True)
        net_id = net["network"]["id"]
        subnet = self._make_subnet(
            self.fmt, net, gateway="10.0.0.1", cidr="10.0.0.0/24"
        )["subnet"]
        self._bind_baremetal_port(net_id, DEFAULT_PHYSNET, "host-a")
        self._bind_baremetal_port(net_id, SECOND_PHYSNET, "host-b")

        with mock.patch(
            "neutron_understack.routers._router_has_flavor", return_value=True
        ):
            router = self._create_router()
            self.l3_plugin.add_router_interface(
                self.context, router["id"], {"subnet_id": subnet["id"]}
            )
            # Isolate the detach from the attach/bind sync calls.
            self.undersync_mock.reset_mock()
            self.l3_plugin.remove_router_interface(
                self.context, router["id"], {"subnet_id": subnet["id"]}
            )

        # Desired: detaching the router reconciles the switches still carrying
        # the network's baremetal ports.
        synced = {
            call.args[0]
            for call in self.undersync_mock.sync.call_args_list
            if call.args
        }
        assert DEFAULT_PHYSNET in synced
        assert SECOND_PHYSNET in synced
