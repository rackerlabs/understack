import importlib.metadata
import logging

from openstack import connection
from openstack.baremetal.baremetal_service import BaremetalService
from openstack.baremetal.v1.node import Node as BaremetalNode
from oslo_config import cfg

from neutron_understack import config

LOG = logging.getLogger(__name__)

# Ironic provision-state targets (verbs) used by the netdev router flavor
# lifecycle. available -> (manage) -> manageable -> (adopt) -> active on adopt;
# manageable -> (provide) -> available to roll back a partial adoption; and
# active -> (deleted/undeploy) -> available (triggering cleaning) on release.
_PROVISION_MANAGE = "manage"
_PROVISION_ADOPT = "adopt"
_PROVISION_PROVIDE = "provide"
_PROVISION_UNDEPLOY = "deleted"

# Stable provision states (not verbs). We wait for adopt to reach "active"
# explicitly rather than via set_node_provision_state(wait=True): the SDK's
# EXPECTED_STATES maps the "adopt" verb to "available" (in
# openstack/baremetal/v1/_common.py), which is wrong -- Ironic drives adopt to
# "active" -- so the built-in wait would poll for the wrong state and time out.
# https://review.opendev.org/c/openstack/openstacksdk/+/999686
# Will remove this ones the changes gets raised
_STATE_ACTIVE = "active"
_STATE_MANAGEABLE = "manageable"
_STATE_AVAILABLE = "available"

# Seconds to wait for each provision-state transition to settle. netdev nodes
# have noop deploy/clean interfaces so these transitions are effectively
# instantaneous, but we still bound the wait so an API worker cannot hang
# forever on an unresponsive Ironic.
_PROVISION_TIMEOUT = 300

# Ironic hardware type for network appliance devices. Router flavors only adopt
# nodes of this driver, so a resource_class shared with other hardware types
# (e.g. servers) cannot cause us to adopt the wrong node.
_NETDEV_DRIVER = "netdev"


class IronicClient:
    def __init__(self):
        config.register_ironic_opts(cfg.CONF)
        self.irclient = self._get_ironic_client()

    def _get_ironic_client(self) -> BaremetalService:
        session = config.get_session(config._OPT_GRP_IRONIC)

        version = importlib.metadata.version("neutron_understack")

        return connection.Connection(
            session=session,
            oslo_conf=cfg.CONF,
            connect_retries=cfg.CONF.http_retries,
            app_name="neutron_understack",
            app_version=version,
        ).baremetal

    def baremetal_node_name(self, node_uuid: str) -> str | None:
        try:
            node = self.irclient.get_node(node_uuid)
            return node.name if node else None
        except Exception:
            return None

    def baremetal_node_uuid(self, node_name: str) -> str | None:
        try:
            node = self.irclient.get_node(node_name)
            return node.id if node else None
        except Exception:
            return None

    def available_node_for_resource_class(
        self, resource_class: str
    ) -> BaremetalNode | None:
        """Return the first available Ironic node with the given resource class.

        Ironic filters server-side by ``driver=netdev``, ``resource_class``,
        ``provision_state=available`` and not-in-maintenance, so any returned
        node is a netdev appliance that is actually usable, in the interchangeable
        pool for this flavor. Selection is first-match; there is no
        scheduling/ranking.
        (WIP circle back here , if there is any rule select netdev).
        """
        try:
            node = next(
                self.irclient.nodes(
                    driver=_NETDEV_DRIVER,
                    resource_class=resource_class,
                    provision_state="available",
                    # Skip nodes an operator has parked in maintenance.
                    # Ironic will still let us adopt such a node, so
                    # without this filter we would silently put a router on
                    # hardware that was deliberately taken out of service.
                    is_maintenance=False,
                    details=True,
                )
            )
        except StopIteration:
            LOG.info(
                "No available netdev node found for resource_class=%s",
                resource_class,
            )
            return None
        LOG.info(
            "Selected available netdev node %s (name=%s) for resource_class=%s",
            node.id,
            node.name,
            resource_class,
        )
        return node

    def node_by_instance_uuid(self, instance_uuid: str) -> BaremetalNode | None:
        """Return the node currently adopted for the given instance UUID."""
        try:
            return next(self.irclient.nodes(instance_id=instance_uuid, details=True))
        except StopIteration:
            return None

    def attach_vif_to_node(self, node: str | BaremetalNode, vif_id: str) -> None:
        """Attach a Neutron port (VIF) to the node."""
        node_id = node.id if isinstance(node, BaremetalNode) else node
        LOG.info("Attaching VIF %s to Ironic node %s", vif_id, node_id)
        self.irclient.attach_vif_to_node(node, vif_id)

    def detach_vif_from_node(self, node: str | BaremetalNode, vif_id: str) -> bool:
        """Detach a VIF from the node.

        Returns whatever the SDK reports (False when the VIF was not attached);
        ``ignore_missing=True`` so tearing down an already-detached VIF is a no-op.
        """
        node_id = node.id if isinstance(node, BaremetalNode) else node
        LOG.info("Detaching VIF %s from Ironic node %s", vif_id, node_id)
        return self.irclient.detach_vif_from_node(node, vif_id, ignore_missing=True)

    def node_vif_ids(self, node: str | BaremetalNode) -> list[str]:
        """Return the Neutron port (VIF) ids currently attached to the node."""
        return self.irclient.list_node_vifs(node)

    def adopt_node_for_router(
        self,
        node: str | BaremetalNode,
        *,
        project_id: str,
        router_id: str,
        router_name: str,
    ) -> None:
        """Adopt a node and bind it to the owning project and router.

        Drives available -> manageable -> active via the Ironic ``adopt`` verb,
        stamping ``lessee`` (owning project), ``instance_uuid`` (router UUID) and
        ``instance_name`` (router name). ``instance_name`` is a distinct field
        from the node's own ``name``, so the node's enrollment name is preserved.
        """
        node_id = node.id if isinstance(node, BaremetalNode) else node
        LOG.info(
            "Adopting node %s for router %s (name=%s project=%s): manage "
            "(available -> manageable)",
            node_id,
            router_id,
            router_name,
            project_id,
        )
        try:
            # available -> manageable, required before the adopt verb is valid.
            # Kept inside the try so a manage failure like the wait timing out
            # after the node already reached manageable, or a concurrent create
            # having claimed the node and is rolled back too, instead of stranding
            # the node in manageable.
            managed = self.irclient.set_node_provision_state(
                node, _PROVISION_MANAGE, wait=True, timeout=_PROVISION_TIMEOUT
            )
            LOG.debug(
                "Node %s provision_state=%s after manage",
                node_id,
                getattr(managed, "provision_state", "?"),
            )
            # Stamp ownership while manageable. A CONFLICT on instance_uuid means
            # the node was claimed by another router concurrently; it is terminal,
            # not a transient lock, so do not retry it.
            LOG.info(
                "Stamping node %s: lessee=%s instance_uuid=%s instance_name=%s",
                node_id,
                project_id,
                router_id,
                router_name,
            )
            self.irclient.update_node(
                node,
                retry_on_conflict=False,
                lessee=project_id,
                instance_id=router_id,
                instance_name=router_name,
            )
            # manageable -> active via adopt (no real deploy for netdev nodes).
            # Issue with wait=False and wait explicitly for "active": the SDK's
            # built-in wait for the "adopt" verb targets "available" (wrong).
            LOG.info("Node %s: adopt (manageable -> active)", node_id)
            self.irclient.set_node_provision_state(node, _PROVISION_ADOPT, wait=False)
            adopted = self.irclient.wait_for_nodes_provision_state(
                [node], _STATE_ACTIVE, timeout=_PROVISION_TIMEOUT
            )[0]
        except Exception:
            # Adopt was not confirmed. The node may be manageable (maybe stamped),
            # still adopting, adopt-failed, or even active if the wait aborted
            # after the transition completed. _return_node_to_available re-reads
            # the state and picks the right recovery, then we re-raise so the
            # caller aborts the router create.
            LOG.warning(
                "Adoption of node %s for router %s failed; rolling back to available",
                node_id,
                router_id,
            )
            self._return_node_to_available(node)
            raise
        LOG.info(
            "Node %s adopted for router %s: provision_state=%s lessee=%s "
            "instance_uuid=%s instance_name=%s",
            node_id,
            router_id,
            adopted.provision_state,
            adopted.lessee,
            adopted.instance_id,
            adopted.instance_name,
        )

    def _return_node_to_available(self, node: str | BaremetalNode) -> None:
        """Return a node to the available pool from whatever state it is in.

        Re-reads the node's current provision state and picks the correct verb,
        because this runs both as adopt rollback (where a timed-out or aborted
        adopt may have left the node ``manageable``, ``active`` or in a failure
        state) and as normal release. Best-effort and guarded so it never masks
        a caller's original error:

        * ``available``  -> just clear any stale ownership stamps;
        * ``manageable`` -> clear our ownership stamps, then ``provide``;
        * ``active``     -> ``undeploy`` (triggers cleaning), then clear ownership
          -- undeploy tears down instance_uuid/instance_name but NOT lessee;
        * anything else (e.g. ``adopt failed``, ``adopting``) -> leave for
          reconciliation rather than issue an invalid transition.
        """
        try:
            node = self.irclient.get_node(node)
        except Exception:
            LOG.exception("Could not fetch node to return it to available")
            return
        node_id = node.id
        state = node.provision_state

        if state == _STATE_AVAILABLE:
            # Already available, but may still carry a lessee from a prior
            # adoption (undeploy does not clear it); make sure it is truly free.
            self._clear_ownership(node, node_id)
        elif state == _STATE_MANAGEABLE:
            LOG.info("Returning node %s to available (clear stamps + provide)", node_id)
            self._clear_ownership(node, node_id)
            self._guarded_provision(node, _PROVISION_PROVIDE, node_id)
        elif state == _STATE_ACTIVE:
            LOG.info("Returning node %s to available (undeploy)", node_id)
            self._guarded_provision(node, _PROVISION_UNDEPLOY, node_id)
            # undeploy clears instance_uuid/instance_name but leaves lessee, so
            # the node would rejoin the pool still leased to the deleted router's
            # project. Clear ownership explicitly.
            self._clear_ownership(node, node_id)
        else:
            LOG.warning(
                "Node %s is in state %s; cannot auto-return it to available, "
                "leaving for reconciliation",
                node_id,
                state,
            )

    def _clear_ownership(self, node: BaremetalNode, node_id: str) -> None:
        """Clear lessee + instance association so the node rejoins the pool free."""
        try:
            self.irclient.update_node(
                node,
                retry_on_conflict=False,
                lessee=None,
                instance_id=None,
                instance_name=None,
            )
            LOG.info("Cleared ownership stamps on node %s", node_id)
        except Exception:
            LOG.exception("Failed to clear ownership on node %s", node_id)

    def _guarded_provision(
        self, node: BaremetalNode, target: str, node_id: str
    ) -> None:
        """Drive a provision-state transition, logging (not raising) on failure."""
        try:
            self.irclient.set_node_provision_state(
                node, target, wait=True, timeout=_PROVISION_TIMEOUT
            )
            LOG.info("Node %s reached available via %s", node_id, target)
        except Exception:
            LOG.exception(
                "Failed to return node %s to available via %s; manual cleanup "
                "may be required",
                node_id,
                target,
            )

    def release_node_for_router(self, router_id: str) -> BaremetalNode | None:
        """Return the router's node to the available pool, whatever its state.

        A fully adopted node is ``active`` and is undeployed (triggering
        cleaning); other states are handled by ``_return_node_to_available``.
        Returns the node, or None if none is bound to this router.
        """
        node = self.node_by_instance_uuid(router_id)
        if node is None:
            return None
        LOG.info(
            "Releasing node %s bound to router %s (current provision_state=%s)",
            node.id,
            router_id,
            node.provision_state,
        )
        self._return_node_to_available(node)
        return node
