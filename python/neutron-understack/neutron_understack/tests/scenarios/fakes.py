"""In-harness fakes for external systems the router path reaches into.

The router uplink path (``neutron_understack.routers``) talks to the OVN
Northbound IDL via ``routers.ovn_client()``. These fakes record the localnet
port operations and make the vxlan-HCG workaround short-circuit, so router
scenarios can run without a real OVN database.
"""

import contextlib
from unittest import mock


class FakeNbIdl:
    """Minimal OVN Northbound IDL: records localnet LSP create/delete."""

    def __init__(self):
        self.created_ports = []
        self.deleted_ports = []

    def create_lswitch_port(self, **kwargs):
        self.created_ports.append(kwargs)
        return mock.MagicMock(name="create_lswitch_port_cmd")

    def delete_lswitch_port(self, **kwargs):
        self.deleted_ports.append(kwargs)
        return mock.MagicMock(name="delete_lswitch_port_cmd")

    def lookup(self, table, name, default=None):
        # Report the per-network HCG as already populated so
        # link_vxlan_network_ha_chassis_group returns early (that workaround has
        # its own dedicated scenario; the uplink scenarios don't exercise it).
        if table == "HA_Chassis_Group":
            return mock.MagicMock(ha_chassis=[mock.MagicMock()])
        return default

    def db_list_rows(self, table):
        cmd = mock.MagicMock()
        cmd.execute.return_value = []
        return cmd

    def transaction(self, **kwargs):
        return contextlib.nullcontext(mock.MagicMock())


class FakeOvnClient:
    """Stand-in for the OVN ML2 driver's ``_ovn_client``."""

    def __init__(self):
        self._nb_idl = FakeNbIdl()
        self._sb_idl = mock.MagicMock()

    def _transaction(self, commands, txn=None):
        return None


class FakeIronicClient:
    """Stand-in for neutron_understack.ironic.IronicClient (netdev pool).

    Models a single-node pool: one node is available until adopted, then the
    router->node mapping is remembered so release can return it. Records the
    adopt/release calls for assertions.
    """

    def __init__(self, node_id="netdev-node-1"):
        self._node = mock.MagicMock(id=node_id)
        self._available = True
        self._by_router = {}
        self.adopted = []
        self.released = []

    def available_node_for_resource_class(self, resource_class):
        return self._node if self._available else None

    def adopt_node_for_router(self, node, project_id, router_id, router_name):
        self._available = False
        self._by_router[router_id] = node
        self.adopted.append(
            {"node": node, "project_id": project_id, "router_id": router_id}
        )
        return node

    def release_node_for_router(self, router_id):
        node = self._by_router.pop(router_id, None)
        if node is not None:
            self._available = True
            self.released.append(router_id)
        return node
