"""Scenario tests for the non-flavored router uplink path (OVN + trunk).

See neutron_understack/tests/scenarios/SCENARIOS.md (RTR-*) for the catalog.
"""

import contextlib
from unittest import mock

import pytest
from neutron.common.ovn import utils as ovn_utils
from neutron.db import segments_db
from neutron_lib import constants as p_const

from neutron_understack.tests.scenarios.base import UnderstackMl2RouterOvnScenarioBase
from neutron_understack.tests.scenarios.fakes import FakeOvnClient


class TestRouterUplink(UnderstackMl2RouterOvnScenarioBase):
    def _plain_port(self, net_id):
        res = self._create_port(self.fmt, net_id, is_admin=True)
        assert res.status_int == 201, res.body
        return self.deserialize(self.fmt, res)["port"]["id"]

    def _make_network_node_trunk(self):
        """Create a stand-in network-node trunk and return its id."""
        nn_net = self._make_network(self.fmt, "nn-net", True)["network"]["id"]
        nn_parent = self._plain_port(nn_net)
        trunk = self.trunk_plugin.create_trunk(
            self.context,
            {
                "trunk": {
                    "port_id": nn_parent,
                    "project_id": self._project_id,
                    "admin_state_up": True,
                    "sub_ports": [],
                }
            },
        )
        return trunk["id"]

    def _router_net_with_subnet(self, name="router-net"):
        net = self._make_network(self.fmt, name, True)
        subnet = self._make_subnet(
            self.fmt, net, gateway="10.20.0.1", cidr="10.20.0.0/24"
        )["subnet"]
        return net["network"]["id"], subnet["id"]

    @contextlib.contextmanager
    def _ovn(self, fake, nn_trunk_id):
        with (
            mock.patch("neutron_understack.routers.ovn_client", return_value=fake),
            mock.patch(
                "neutron_understack.utils.fetch_network_node_trunk_id",
                return_value=nn_trunk_id,
            ),
        ):
            yield

    def _shared_uplink_ports(self, net_id):
        ports = self.core_plugin.get_ports(
            self.context, filters={"network_id": [net_id]}
        )
        return [p for p in ports if (p.get("name") or "").startswith("uplink-")]

    @pytest.mark.scenario("RTR-ATTACH-01")
    def test_nonflavored_router_attach_builds_uplink(self):
        nn_trunk_id = self._make_network_node_trunk()
        net_id, subnet_id = self._router_net_with_subnet()
        fake = FakeOvnClient()
        router = self._create_router()

        with self._ovn(fake, nn_trunk_id):
            self.l3_plugin.add_router_interface(
                self.context, router["id"], {"subnet_id": subnet_id}
            )

        shared_ports = self._shared_uplink_ports(net_id)
        assert len(shared_ports) == 1
        shared_port = shared_ports[0]
        segment_id = shared_port["name"].removeprefix("uplink-")
        segment = segments_db.get_segment_by_id(self.context, segment_id)
        assert segment[segments_db.NETWORK_TYPE] == p_const.TYPE_VLAN
        assert segment[segments_db.PHYSICAL_NETWORK] == self.NETWORK_NODE_PHYSNET

        assert self._trunk_subports(nn_trunk_id) == [
            {
                "port_id": shared_port["id"],
                "segmentation_type": p_const.TYPE_VLAN,
                "segmentation_id": segment[segments_db.SEGMENTATION_ID],
            }
        ]

        assert len(fake._nb_idl.created_ports) == 1, fake._nb_idl.created_ports
        created = fake._nb_idl.created_ports[0]
        assert created["lswitch_name"] == ovn_utils.ovn_name(net_id)
        assert created["lport_name"] == shared_port["name"]
        assert created["type"] == "localnet"
        assert created["tag"] == segment[segments_db.SEGMENTATION_ID]
        assert created["options"]["network_name"] == self.NETWORK_NODE_PHYSNET

    @pytest.mark.scenario("RTR-SECOND-01")
    def test_second_router_on_network_is_noop(self):
        nn_trunk_id = self._make_network_node_trunk()
        # One network, two subnets (routers can't share a subnet's gateway IP).
        net = self._make_network(self.fmt, "router-net", True)
        net_id = net["network"]["id"]
        subnet_a = self._make_subnet(
            self.fmt, net, gateway="10.20.0.1", cidr="10.20.0.0/24"
        )["subnet"]
        subnet_b = self._make_subnet(
            self.fmt, net, gateway="10.21.0.1", cidr="10.21.0.0/24"
        )["subnet"]
        fake = FakeOvnClient()
        router_a = self._create_router()
        router_b = self._create_router()

        with self._ovn(fake, nn_trunk_id):
            self.l3_plugin.add_router_interface(
                self.context, router_a["id"], {"subnet_id": subnet_a["id"]}
            )
            self.l3_plugin.add_router_interface(
                self.context, router_b["id"], {"subnet_id": subnet_b["id"]}
            )

        # Only the first router built the uplink; the second is a no-op.
        assert len(fake._nb_idl.created_ports) == 1, fake._nb_idl.created_ports
        assert len(self._shared_uplink_ports(net_id)) == 1

    @pytest.mark.scenario("RTR-DETACH-01")
    def test_remove_router_interface_tears_down_uplink(self):
        nn_trunk_id = self._make_network_node_trunk()
        net_id, subnet_id = self._router_net_with_subnet()
        fake = FakeOvnClient()
        router = self._create_router()

        with (
            self._ovn(fake, nn_trunk_id),
            mock.patch.object(
                self.trunk_plugin,
                "remove_subports",
                wraps=self.trunk_plugin.remove_subports,
            ) as remove_subports,
        ):
            self.l3_plugin.add_router_interface(
                self.context, router["id"], {"subnet_id": subnet_id}
            )
            shared_port = self._shared_uplink_ports(net_id)[0]
            segment_id = shared_port["name"].removeprefix("uplink-")
            self.l3_plugin.remove_router_interface(
                self.context, router["id"], {"subnet_id": subnet_id}
            )

        remove_subports.assert_called_once_with(
            context=mock.ANY,
            trunk_id=nn_trunk_id,
            subports={"sub_ports": [{"port_id": shared_port["id"]}]},
        )
        assert self._shared_uplink_ports(net_id) == []
        assert fake._nb_idl.deleted_ports == [
            {
                "lport_name": f"uplink-{segment_id}",
                "lswitch_name": ovn_utils.ovn_name(net_id),
            },
            {
                "lport_name": shared_port["id"],
                "lswitch_name": ovn_utils.ovn_name(net_id),
            },
        ]
