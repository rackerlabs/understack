"""Scenario tests for SVI router interface attach vs. bound baremetal ports.

Extends the VRF scenario (VRF-RTR-01) to the SVI router flavor. See
neutron_understack/tests/scenarios/SCENARIOS.md (SVI-RTR-*) for the catalog.
"""

import contextlib
from unittest import mock

import pytest
from neutron.plugins.ml2.common import exceptions as ml2_exc

from neutron_understack.tests.scenarios.base import DEFAULT_PHYSNET
from neutron_understack.tests.scenarios.base import SECOND_PHYSNET
from neutron_understack.tests.scenarios.base import UnderstackMl2RouterScenarioBase


class TestSviRouterInterface(UnderstackMl2RouterScenarioBase):
    @contextlib.contextmanager
    def _as_svi_router(self):
        """Treat the router as SVI-flavored (skip OVN uplink, run SVI checks)."""
        with (
            mock.patch(
                "neutron_understack.routers._router_has_flavor", return_value=True
            ),
            mock.patch(
                "neutron_understack.l3_router.svi._is_svi_router", return_value=True
            ),
        ):
            yield

    def _scoped_ipv4_subnet(
        self,
        network,
        name="svi",
        pool_prefix="10.0.0.0/16",
        cidr="10.0.0.0/24",
        gateway="10.0.0.1",
    ):
        """Create an IPv4 subnet in its own address scope (SVI routers need one)."""
        scope = self.core_plugin.create_address_scope(
            self.context,
            {
                "address_scope": {
                    "name": f"{name}-scope",
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
                    "name": f"{name}-pool",
                    "prefixes": [pool_prefix],
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
            gateway=gateway,
            cidr=cidr,
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

        # Create an SVI router and attach the scoped subnet on the internal side.
        # The SVI flavor is simulated via _as_svi_router(); the scope validation
        # passes because the subnet is address-scoped.
        with self._as_svi_router():
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

    def _attach_expecting_reject(self, subnet_id, router_id):
        # The SVI scope validator raises BadRequest in create_port_precommit,
        # which the ML2 manager wraps in MechanismDriverError.
        with self._as_svi_router(), pytest.raises(ml2_exc.MechanismDriverError):
            self.l3_plugin.add_router_interface(
                self.context, router_id, {"subnet_id": subnet_id}
            )

    @pytest.mark.scenario("SVI-VAL-NOSCOPE-01")
    def test_svi_rejects_subnet_without_address_scope(self):
        net = self._make_network(self.fmt, "n", True)
        subnet = self._make_subnet(
            self.fmt, net, gateway="10.5.0.1", cidr="10.5.0.0/24"
        )["subnet"]
        router = self._create_router()
        self._attach_expecting_reject(subnet["id"], router["id"])

    @pytest.mark.scenario("SVI-VAL-IPV6-01")
    def test_svi_rejects_ipv6_subnet(self):
        net = self._make_network(self.fmt, "n", True)
        subnet = self._make_subnet(
            self.fmt,
            net,
            gateway="fe80::1",
            cidr="fe80::/64",
            ip_version=6,
        )["subnet"]
        router = self._create_router()
        self._attach_expecting_reject(subnet["id"], router["id"])

    @pytest.mark.scenario("SVI-VAL-CONFLICT-01")
    def test_svi_rejects_conflicting_address_scopes(self):
        net_a = self._make_network(self.fmt, "net-a", True)
        subnet_a = self._scoped_ipv4_subnet(
            net_a,
            name="a",
            pool_prefix="10.1.0.0/16",
            cidr="10.1.0.0/24",
            gateway="10.1.0.1",
        )
        net_b = self._make_network(self.fmt, "net-b", True)
        subnet_b = self._scoped_ipv4_subnet(
            net_b,
            name="b",
            pool_prefix="10.2.0.0/16",
            cidr="10.2.0.0/24",
            gateway="10.2.0.1",
        )
        router = self._create_router()
        # First subnet (scope A) attaches cleanly.
        with self._as_svi_router():
            self.l3_plugin.add_router_interface(
                self.context, router["id"], {"subnet_id": subnet_a["id"]}
            )
        # Second subnet has a different scope -> rejected.
        self._attach_expecting_reject(subnet_b["id"], router["id"])
