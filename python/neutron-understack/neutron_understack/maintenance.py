"""Periodics run in the OVN maintenance worker.

Neutron and Ironic share no transaction, so an adopt can outlive a failed
router-row insert and a release can fail after the row is gone. Either way a
node is left stamped with a router that does not exist. No synchronous callback
closes that window, so this periodic sweeps it up.

Reconciles Ironic nodes only; gateway/subnet wiring is out of scope.
"""

# Recheck has_lock_periodic and MAINTENANCE_NB_IDL_LOCK_NAME on every Neutron
# upgrade because they are internal Neutron APIs.
from neutron.objects import router as l3_obj
from neutron.plugins.ml2.drivers.ovn.mech_driver.ovsdb import maintenance
from neutron_lib import context as n_context
from oslo_config import cfg
from oslo_log import log as logging

from neutron_understack import config
from neutron_understack.ironic import IronicClient

LOG = logging.getLogger(__name__)
RECONCILE_SPACING = 600


class NetdevRouterMaintenancePeriodics:
    """Reconcile netdev-router Ironic state from the OVN maintenance worker.

    Release orphaned Palo Alto nodes to available, or park failed nodes in
    manageable for operator recovery.
    """

    def __init__(self, plugin, ovn_client):
        self._plugin = plugin
        config.register_netdev_reconcile_opts(cfg.CONF)
        # (node_id, router_id) pairs seen orphaned last pass. See
        # _reconcile_once for why both halves of the key matter.
        self._orphans_seen: set[tuple[str, str]] = set()
        # Take the maintenance lock so exactly one neutron-server runs these
        # periodics.
        self._idl = ovn_client._nb_idl.idl
        self._idl.set_lock(maintenance.MAINTENANCE_NB_IDL_LOCK_NAME)

    @property
    def has_lock(self):
        return self._idl.has_lock

    def _ironic(self) -> IronicClient:
        """Build the client during a pass and reuse it.

        Use a method: Neutron evaluates properties during job registration,
        outside the pass's error handler.
        """
        try:
            return self._ironic_ref
        except AttributeError:
            self._ironic_ref = IronicClient()
            return self._ironic_ref

    @maintenance.has_lock_periodic(spacing=RECONCILE_SPACING, run_immediately=False)
    def reconcile_netdev_routers(self):
        if not cfg.CONF.netdev_router_reconcile.enabled:
            self._orphans_seen.clear()
            LOG.debug("netdev-router reconcile is disabled; skipping")
            return
        try:
            self._reconcile_once()
        except Exception:
            # A failed scan cannot confirm consecutive orphan observations.
            self._orphans_seen.clear()
            LOG.exception("netdev-router reconcile pass failed")

    def _reconcile_once(self):
        """Release netdev nodes bound to routers that no longer exist.

        Adoption stamps the node before the router row is inserted, so a
        router being created right now is indistinguishable from an orphan.
        Two consecutive sightings put a full interval between the two, with no
        dependence on Ironic and neutron-server agreeing on the clock.

        Keyed on (node, router): a node re-adopted by a different router must
        not inherit the old sighting.
        """
        dry_run = cfg.CONF.netdev_router_reconcile.dry_run
        context = n_context.get_admin_context()

        orphans_now = set()
        for node in self._ironic().panos_reconcile_nodes():
            router_id = IronicClient.router_id_for_release(node)
            if not router_id:
                # A pending release marker survives Ironic clearing instance_uuid.
                # Unmarked nodes and conflicting ownership are not ours to release.
                continue
            if l3_obj.Router.objects_exist(context, id=router_id):
                continue
            orphans_now.add((node.id, router_id))

        confirmed = orphans_now & self._orphans_seen
        # Only carry forward what is still orphaned, so a node that got a live
        # router back does not stay armed for release.
        self._orphans_seen = orphans_now

        if not orphans_now:
            LOG.debug("netdev-router reconcile: no orphaned nodes")
            return

        LOG.info(
            "netdev-router reconcile: %d orphaned node(s), %d confirmed by a "
            "previous pass%s",
            len(orphans_now),
            len(confirmed),
            " (dry run)" if dry_run else "",
        )

        for node_id, router_id in sorted(orphans_now - confirmed):
            LOG.info(
                "Node %s is stamped with router %s which does not exist; "
                "deferring release until the next pass confirms it",
                node_id,
                router_id,
            )

        for node_id, router_id in sorted(confirmed):
            if not self.has_lock:
                self._orphans_seen.clear()
                return
            if dry_run:
                LOG.info(
                    "netdev-router reconcile (dry run): would release node %s "
                    "for nonexistent router %s",
                    node_id,
                    router_id,
                )
                continue
            self._release_orphan(node_id, router_id)

    def _release_orphan(self, node_id: str, router_id: str) -> None:
        """Return one orphaned node to the available pool.

        Recheck desired state after the scan: earlier nodes may have taken time
        to release. Ironic then rereads this exact node and verifies ownership
        and maintenance status before acting. Its durable release marker keeps
        partial cleanup discoverable across passes and worker restarts.
        """
        try:
            if l3_obj.Router.objects_exist(n_context.get_admin_context(), id=router_id):
                self._orphans_seen.discard((node_id, router_id))
                return
            LOG.info(
                "Releasing orphaned netdev node %s for nonexistent router %s",
                node_id,
                router_id,
            )
            complete = self._ironic().release_orphan_node(node_id, router_id)
        except Exception:
            LOG.exception(
                "Failed to release orphaned netdev node %s (router %s); will "
                "retry on the next pass",
                node_id,
                router_id,
            )
            return
        if complete:
            self._orphans_seen.discard((node_id, router_id))
