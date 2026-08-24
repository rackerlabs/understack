"""Scenario tests for SVI router interface attach vs. bound baremetal ports.

Extends the VRF scenario (VRF-RTR-01) to the SVI router flavor. See
neutron_understack/tests/scenarios/SCENARIOS.md (SVI-RTR-*) for the catalog.
"""

from unittest import mock

import pytest

from neutron_understack.tests.scenarios.base import DEFAULT_PHYSNET
from neutron_understack.tests.scenarios.base import SECOND_PHYSNET
from neutron_understack.tests.scenarios.base import UnderstackMl2RouterScenarioBase


class TestSviRouterInterface(UnderstackMl2RouterScenarioBase):
    def _scoped_ipv4_subnet(self, network):
        """Create an IPv4 subnet in an address scope (SVI routers require one)."""
        scope = self.core_plugin.create_address_scope(
            self.context,
            {
                "address_scope": {
                    "name": "svi-scope",
                    "ip_version": 4,
                    "shared": False,
                    "tenant_id": self._project_id,
                }
            },
        )
        pool = self.core_plugin.create_subnetpool(
            self.context,
            {
                "subnetpool": {
                    "name": "svi-pool",
                    "prefixes": ["10.0.0.0/16"],
                    "address_scope_id": scope["id"],
                    "default_prefixlen": 24,
                    "min_prefixlen": 8,
                    "max_prefixlen": 32,
                    "shared": False,
                    "is_default": False,
                    "tenant_id": self._project_id,
                }
            },
        )
        return self._make_subnet(
            self.fmt,
            network,
            gateway="10.0.0.1",
            cidr="10.0.0.0/24",
            subnetpool_id=pool["id"],
        )["subnet"]

    # BUG: like the VRF case (#2240), attaching an SVI router interface does not
    # reconcile the switches carrying the network's already-bound baremetal
    # ports -- undersync is never asked to sync those physnets. Asserts the
    # desired behavior; strict=True flips to a failure once fixed.
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "understack#2240: SVI router interface attach does not sync the "
            "physnets of baremetal ports already bound on the network"
        ),
    )
    @pytest.mark.scenario("SVI-RTR-01")
    def test_svi_router_interface_syncs_bound_port_physnets(self):
        net = self._make_network(self.fmt, "vxlan-net", True)
        net_id = net["network"]["id"]
        subnet = self._scoped_ipv4_subnet(net)

        # Two baremetal ports on this network, bound to different physnets.
        self._bind_baremetal_port(net_id, DEFAULT_PHYSNET, "host-a")
        self._bind_baremetal_port(net_id, SECOND_PHYSNET, "host-b")

        # Isolate the router attach from the sync calls made during the binds.
        self.undersync_mock.reset_mock()

        # Create an SVI (flavored) router and attach the scoped subnet on the
        # internal side. The SVI flavor is simulated by patching the flavor
        # detection seams, mirroring the unit tests: _router_has_flavor gates the
        # (skipped) uplink path, and svi._is_svi_router drives the precommit SVI
        # scope validation, which passes because the subnet is address-scoped.
        with (
            mock.patch(
                "neutron_understack.routers._router_has_flavor", return_value=True
            ),
            mock.patch(
                "neutron_understack.l3_router.svi._is_svi_router", return_value=True
            ),
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
