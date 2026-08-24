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
