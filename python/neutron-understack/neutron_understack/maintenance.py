"""Periodics run in the OVN maintenance worker.

Proves the mechanism fires end to end (hook discovered, worker runs, once
cluster-wide) before the real reconciliation logic is added.
"""

# NOTE: Re-verify these symbols still exist on every neutron upgrade has_lock_periodic
# and MAINTENANCE_NB_IDL_LOCK_NAME coz they are neutron-internal module.
from neutron.plugins.ml2.drivers.ovn.mech_driver.ovsdb import maintenance
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
RECONCILE_SPACING = 600  # Temp


class NetdevRouterMaintenancePeriodics:
    """Reconcile netdev-router Ironic state from the OVN maintenance worker.

    Body is a no-op log line.
    """

    def __init__(self, plugin, ovn_client):
        self._plugin = plugin
        # Take the maintenance lock so exactly one neutron-server runs these
        # periodics.
        LOG.warning(
            "NETDEV periodic __init__; _nb_idl=%r",
            getattr(ovn_client, "_nb_idl", "MISSING"),
        )
        self._idl = ovn_client._nb_idl.idl
        self._idl.set_lock(maintenance.MAINTENANCE_NB_IDL_LOCK_NAME)

    @property
    def has_lock(self):
        return self._idl.has_lock

    @maintenance.has_lock_periodic(spacing=RECONCILE_SPACING, run_immediately=False)
    def reconcile_netdev_routers(self):
        # No-op: proves the periodic is scheduled and fires on exactly one
        # neutron-server. host= lets us confirm it is not firing per-worker.
        LOG.debug("netdev-router reconcile: placeholder, no action yet")
