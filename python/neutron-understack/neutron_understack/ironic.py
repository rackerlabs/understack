import importlib.metadata
import logging
from dataclasses import dataclass

from openstack import connection
from openstack import exceptions as sdk_exc
from openstack.baremetal.baremetal_service import BaremetalService
from openstack.baremetal.v1.node import Node as BaremetalNode
from oslo_config import cfg

from neutron_understack import config

LOG = logging.getLogger(__name__)

# Ironic provision-state targets (verbs) used by the netdev router flavor
# lifecycle. available -> (manage) -> manageable -> (adopt) -> active on adopt;
# and active -> (deleted/undeploy) -> available (triggering cleaning) on
# release. Failed adoption/cleaning is recovered to manageable and parked.
_PROVISION_MANAGE = "manage"
_PROVISION_ADOPT = "adopt"
_PROVISION_UNDEPLOY = "deleted"

_STATE_ACTIVE = "active"
_STATE_ADOPT_FAILED = "adopt failed"
_STATE_CLEAN_FAILED = "clean failed"
_STATE_MANAGEABLE = "manageable"
_STATE_AVAILABLE = "available"

# Seconds to wait for each provision-state transition to settle. netdev nodes
# have noop deploy/clean interfaces so these transitions are effectively
# instantaneous, but we still bound the wait so an API worker cannot hang
# forever on an unresponsive Ironic.
_PROVISION_TIMEOUT = 300
_RECONCILE_PROVISION_TIMEOUT = 60
_PANOS_DRIVER = "panos"
_ROUTER_RELEASE_MARKER = "understack_router_release"  # release is in progress


@dataclass(frozen=True)
class NodeReleaseResult:
    """Outcome of looking up and releasing a router's Ironic node."""

    node: BaremetalNode | None
    released: bool


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

        Select the first matching Palo Alto node, excluding maintenance,
        instance associations and pending releases. No ranking is applied.
        """
        for node in self.irclient.nodes(
            driver=_PANOS_DRIVER,
            resource_class=resource_class,
            provision_state="available",
            is_maintenance=False,
            details=True,
        ):
            # Already claimed, or reserved by a release still cleaning up.
            if node.instance_id or _ROUTER_RELEASE_MARKER in (node.extra or {}):
                continue
            LOG.info(
                "Selected available Palo Alto node %s (name=%s) for resource_class=%s",
                node.id,
                node.name,
                resource_class,
            )
            return node
        LOG.info(
            "No available Palo Alto node found for resource_class=%s",
            resource_class,
        )
        return None

    def node_by_instance_uuid(self, instance_uuid: str) -> BaremetalNode | None:
        """Return the node currently adopted for the given instance UUID."""
        try:
            return next(self.irclient.nodes(instance_id=instance_uuid, details=True))
        except StopIteration:
            return None

    def panos_reconcile_nodes(self) -> list[BaremetalNode]:
        """Find bound nodes, and releases whose association was cleared.

        Scoped by driver, so another ``netdev`` consumer's node is never a
        candidate. A node whose stamp never landed is not discoverable here.
        """
        return [
            node
            for node in self.irclient.nodes(
                driver=_PANOS_DRIVER,
                is_maintenance=False,
                details=True,
            )
            if self._is_router_reconcile_candidate(node)
        ]

    @staticmethod
    def _is_router_reconcile_candidate(node: BaremetalNode) -> bool:
        extra = node.extra or {}
        if not isinstance(extra, dict):
            return False
        return bool(node.instance_id) or _ROUTER_RELEASE_MARKER in extra

    @staticmethod
    def router_id_for_release(node: BaremetalNode) -> str | None:
        """Resolve ownership without authorizing a conflicting release marker."""
        extra = node.extra or {}
        if not isinstance(extra, dict):
            return None
        identities = []
        marker = extra.get(_ROUTER_RELEASE_MARKER)
        if _ROUTER_RELEASE_MARKER in extra:
            if not isinstance(marker, str) or not marker:
                return None
            identities.append(marker)
        instance_id = node.instance_id
        if instance_id:
            if not isinstance(instance_id, str):
                return None
            identities.append(instance_id)
        if not identities or len(set(identities)) != 1:
            return None
        return identities[0]

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

        Identity is stamped after manage; earlier failures need manual recovery.
        Concurrent claims remain a separate concern.
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
            # Attempt identity-checked rollback if manage or a later step fails.
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
            LOG.info("Node %s: adopt (manageable -> active)", node_id)
            # Use wait=False: the SDK waits for available after adopt, not active.
            # https://review.opendev.org/c/openstack/openstacksdk/+/999686
            self.irclient.set_node_provision_state(node, _PROVISION_ADOPT, wait=False)
            adopted = self.irclient.wait_for_nodes_provision_state(
                [node], _STATE_ACTIVE, timeout=_PROVISION_TIMEOUT
            )[0]
        except Exception:
            LOG.warning(
                "Adoption of node %s for router %s failed; rolling back to available",
                node_id,
                router_id,
            )
            self._return_node_to_available(node_id, router_id)
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

    def _return_node_to_available(
        self,
        node: str | BaremetalNode,
        router_id: str,
        *,
        timeout: int = _PROVISION_TIMEOUT,
    ) -> bool:
        """Best-effort release, keeping the node discoverable until it is clean.

        Marks before transitioning, since undeploy clears the instance fields
        even when it fails. Acts only on a node whose router identity still
        matches, so a failed create cannot undo another one's work. A healthy
        active release ends in ``available``; a failed transition parks in
        ``manageable``.
        """
        try:
            current = self.irclient.get_node(node)
            if current is None:
                return True
            if current.driver != _PANOS_DRIVER or current.is_maintenance:
                return False
            extra = current.extra or {}
            if self.router_id_for_release(current) != router_id:
                LOG.warning(
                    "Node %s no longer belongs to router %s", current.id, router_id
                )
                return False
            state = current.provision_state
            targets = {
                _STATE_ADOPT_FAILED: _PROVISION_MANAGE,
                _STATE_CLEAN_FAILED: _PROVISION_MANAGE,
                _STATE_ACTIVE: _PROVISION_UNDEPLOY,
                # Ironic's failed undeploy enters error; deleted retries it.
                "error": _PROVISION_UNDEPLOY,
            }
            # Parked in manageable: identity cleared, but kept out of the
            # pool so a node that just failed a transition is not reused.
            park_manageable = state in {
                _STATE_MANAGEABLE,
                _STATE_ADOPT_FAILED,
                _STATE_CLEAN_FAILED,
            }
            if (
                state != _STATE_AVAILABLE
                and state != _STATE_MANAGEABLE
                and state not in targets
            ):
                LOG.warning(
                    "Node %s is in state %s; deferring release for router %s",
                    current.id,
                    state,
                    router_id,
                )
                return False

            if _ROUTER_RELEASE_MARKER not in extra:
                marker_patch = (
                    {
                        "op": "add",
                        "path": f"/extra/{_ROUTER_RELEASE_MARKER}",
                        "value": router_id,
                    }
                    if isinstance(current.extra, dict)
                    else {
                        "op": "add",
                        "path": "/extra",
                        "value": {_ROUTER_RELEASE_MARKER: router_id},
                    }
                )
                self.irclient.patch_node(
                    current,
                    [marker_patch],
                    retry_on_conflict=False,
                )
            # Re-read: the marker patch and the provision transition lock
            # independently, and nothing binds the two atomically. (Ironic's
            # conductor does guard instance_uuid against overwrite, but that
            # protects a different field than this.)
            current = self.irclient.get_node(current.id)
            if not self._release_matches(current, router_id):
                return False
            if current.provision_state != state:
                return False

            # One transition for most states; ``adopt failed`` and
            # ``clean failed`` need manage first. Bounded so an unexpected
            # state cannot spin an API worker.
            for _step in range(2):
                state = current.provision_state
                if state == _STATE_AVAILABLE:
                    break
                if state in {_STATE_ADOPT_FAILED, _STATE_CLEAN_FAILED}:
                    park_manageable = True
                if state == _STATE_MANAGEABLE:
                    park_manageable = True
                    break
                target = targets.get(state)
                if target is None:
                    LOG.warning(
                        "Node %s moved to state %s while releasing router %s; "
                        "deferring",
                        current.id,
                        state,
                        router_id,
                    )
                    return False
                self.irclient.set_node_provision_state(
                    current, target, wait=True, timeout=timeout
                )
                current = self.irclient.get_node(current.id)
                if not self._release_matches(current, router_id):
                    return False
            final_state = _STATE_MANAGEABLE if park_manageable else _STATE_AVAILABLE
            if current.provision_state != final_state or not self._release_matches(
                current, router_id
            ):
                return False
            # One patch, touching only our own keys.
            cleanup_patch = [
                {"op": "add", "path": "/lessee", "value": None},
                {"op": "add", "path": "/instance_uuid", "value": None},
                {"op": "add", "path": "/instance_name", "value": None},
            ]
            cleanup_patch.append(
                {"op": "remove", "path": f"/extra/{_ROUTER_RELEASE_MARKER}"}
            )
            self.irclient.patch_node(
                current,
                cleanup_patch,
                retry_on_conflict=False,
            )
            current = self.irclient.get_node(current.id)
            return (
                current.provision_state == final_state
                and not current.instance_id
                and not current.instance_name
                and not current.lessee
                and _ROUTER_RELEASE_MARKER not in (current.extra or {})
            )
        except sdk_exc.NotFoundException:
            # A removed Ironic node has nothing left to release.
            return True
        except Exception:
            LOG.exception(
                "Failed to release node %s for router %s; will retry", node, router_id
            )
            return False

    def _release_matches(self, node: BaremetalNode | None, router_id: str) -> bool:
        if node is None:
            return False
        extra = node.extra or {}
        if not isinstance(extra, dict):
            return False
        return (
            node.driver == _PANOS_DRIVER
            and not node.is_maintenance
            and self.router_id_for_release(node) == router_id
            and extra.get(_ROUTER_RELEASE_MARKER) == router_id
        )

    def release_orphan_node(self, node_id: str, router_id: str) -> bool:
        """Release the exact confirmed orphan, returning cleanup completion."""
        return self._return_node_to_available(
            node_id, router_id, timeout=_RECONCILE_PROVISION_TIMEOUT
        )

    def release_node_for_router(self, router_id: str) -> NodeReleaseResult:
        """Release the router's node and clear its ownership, whatever its state.

        A fully adopted node is ``active`` and is undeployed (triggering
        cleaning); failed or already manageable nodes are parked in
        ``manageable`` after ownership cleanup.
        """
        node = self.node_by_instance_uuid(router_id)
        if node is None:
            return NodeReleaseResult(node=None, released=False)
        LOG.info(
            "Releasing node %s bound to router %s (current provision_state=%s)",
            node.id,
            router_id,
            node.provision_state,
        )
        return NodeReleaseResult(
            node=node,
            released=self._return_node_to_available(node, router_id),
        )
