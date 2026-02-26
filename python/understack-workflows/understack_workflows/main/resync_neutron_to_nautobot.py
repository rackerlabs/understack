"""Resync Neutron networks and subnets to Nautobot.

Use when Nautobot gets out of sync with Neutron, e.g., after:
- Nautobot database restore
- Missed events
- Manual Nautobot changes

Should be run before resync-ironic-nautobot to ensure IPAM namespaces
and prefixes exist before device/interface sync.
"""

import argparse
import logging
from dataclasses import dataclass

import pynautobot

from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.nautobot import NautobotRequestError
from understack_workflows.openstack.client import get_openstack_client
from understack_workflows.oslo_event.neutron_network import NetworkEvent
from understack_workflows.oslo_event.neutron_network import _create_nautobot_ucvni
from understack_workflows.oslo_event.neutron_network import (
    _ensure_nautobot_ipam_namespace_exists,
)
from understack_workflows.oslo_event.neutron_subnet import _create_nautobot_prefix
from understack_workflows.oslo_event.neutron_subnet import _update_nautobot_prefix

logger = logging.getLogger(__name__)

_EXIT_SUCCESS = 0
_EXIT_SYNC_FAILURES = 1


@dataclass
class SyncResult:
    """Result of a sync operation."""

    total: int = 0
    failed: int = 0

    @property
    def succeeded(self) -> int:
        return self.total - self.failed


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resync Neutron to Nautobot")
    parser.add_argument(
        "--network",
        type=str,
        default="",
        help="Sync specific network UUID (default: all networks)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List resources without syncing"
    )
    parser.add_argument(
        "--ucvni-group",
        type=str,
        help="UCVNI group name (defaults to UCVNI_GROUP_NAME env var)",
    )
    parser = parser_nautobot_args(parser)
    return parser


def _update_nautobot_ucvni(
    nautobot: pynautobot.api,
    event: NetworkEvent,
    ucvni_group_name: str | None = None,
) -> bool:
    """Update existing UCVNI. Returns True if updated, False if not found."""
    import os

    ucvni_id = str(event.network_uuid)

    if ucvni_group_name is None:
        ucvni_group_name = os.getenv("UCVNI_GROUP_NAME")
    if ucvni_group_name is None:
        raise RuntimeError("Please set environment variable UCVNI_GROUP_NAME")

    payload = {
        "name": event.network_name,
        "status": {"name": "Active"},
        "tenant": str(event.tenant_id),
        "ucvni_group": {"name": ucvni_group_name},
        "ucvni_id": event.provider_segmentation_id,
    }

    try:
        response = nautobot.plugins.undercloud_vni.ucvnis.update(
            id=ucvni_id, data=payload
        )
        logger.info("Updated Nautobot UCVNI: %s", response)
        return True
    except pynautobot.RequestError as e:
        if e.req.status_code == 404:
            logger.debug("No pre-existing Nautobot UCVNI with id=%s", ucvni_id)
            return False
        raise NautobotRequestError(e) from e


def sync_network(
    network,
    nautobot: pynautobot.api,
    ucvni_group_name: str | None = None,
) -> bool:
    """Sync a single network to Nautobot.

    Returns True on success, False on failure.
    """
    try:
        network_id = network.id

        # Create NetworkEvent-like object for reuse of existing functions
        event = NetworkEvent(
            event_type="network.sync",
            network_uuid=network_id,
            network_name=network.name,
            tenant_id=network.project_id,
            external=network.is_router_external or False,
            provider_segmentation_id=network.provider_segmentation_id or 0,
        )

        # Create IPAM namespace
        _ensure_nautobot_ipam_namespace_exists(nautobot, str(network_id))

        # Create or update UCVNI if segmentation ID exists
        if event.provider_segmentation_id:
            if not _update_nautobot_ucvni(nautobot, event, ucvni_group_name):
                _create_nautobot_ucvni(nautobot, event, ucvni_group_name)

        return True
    except Exception:
        logger.exception("Failed to sync network %s", network.id)
        return False


def sync_subnet(
    subnet,
    nautobot: pynautobot.api,
    network_external_map: dict[str, bool],
) -> bool:
    """Sync a single subnet to Nautobot.

    Args:
        subnet: OpenStack subnet object
        nautobot: Nautobot API instance
        network_external_map: Dict mapping network_id -> is_router_external

    Returns True on success, False on failure.
    """
    try:
        subnet_id = str(subnet.id)
        network_id = str(subnet.network_id)

        # Determine namespace - external network subnets go to Global namespace
        is_external = network_external_map.get(network_id, False)
        namespace = "Global" if is_external else network_id

        payload = {
            "id": subnet_id,
            "prefix": subnet.cidr,
            "status": "Active",
            "namespace": {"name": namespace},
            "tenant": {"id": str(subnet.project_id)},
        }

        # Try update first, then create
        if not _update_nautobot_prefix(nautobot, subnet_id, payload):
            _create_nautobot_prefix(nautobot, payload)

        return True
    except Exception:
        logger.exception("Failed to sync subnet %s", subnet.id)
        return False


def sync_neutron_to_nautobot(
    nautobot: pynautobot.api,
    network_id: str | None = None,
    ucvni_group_name: str | None = None,
    dry_run: bool = False,
) -> tuple[SyncResult, SyncResult]:
    """Sync Neutron networks and subnets to Nautobot.

    Args:
        nautobot: Nautobot API instance
        network_id: Optional specific network UUID to sync
        ucvni_group_name: UCVNI group name for network sync
        dry_run: If True, only log what would be synced

    Returns:
        Tuple of (network_result, subnet_result)
    """
    conn = get_openstack_client()

    network_result = SyncResult()
    subnet_result = SyncResult()

    # Get networks
    if network_id:
        networks = [conn.network.get_network(network_id)]  # type: ignore[attr-defined]
    else:
        networks = list(conn.network.networks())  # type: ignore[attr-defined]

    # Build network external map for subnet sync
    network_external_map: dict[str, bool] = {}

    # Sync networks first (creates namespaces)
    for network in networks:
        network_result.total += 1
        network_external_map[network.id] = network.is_router_external or False

        if dry_run:
            logger.info(
                "Would sync network: %s (%s) seg_id=%s external=%s",
                network.id,
                network.name,
                network.provider_segmentation_id,
                network.is_router_external,
            )
            continue

        logger.info("Syncing network: %s (%s)", network.id, network.name)
        if not sync_network(network, nautobot, ucvni_group_name):
            network_result.failed += 1

    # Get subnets
    if network_id:
        subnets = list(conn.network.subnets(network_id=network_id))  # type: ignore[attr-defined]
    else:
        subnets = list(conn.network.subnets())  # type: ignore[attr-defined]

    # Sync subnets (creates prefixes)
    for subnet in subnets:
        subnet_result.total += 1

        if dry_run:
            network_is_external = network_external_map.get(subnet.network_id, False)
            logger.info(
                "Would sync subnet: %s (%s) cidr=%s network_external=%s",
                subnet.id,
                subnet.name,
                subnet.cidr,
                network_is_external,
            )
            continue

        logger.info(
            "Syncing subnet: %s (%s) cidr=%s", subnet.id, subnet.name, subnet.cidr
        )
        if not sync_subnet(subnet, nautobot, network_external_map):
            subnet_result.failed += 1

    return network_result, subnet_result


def main() -> int:
    setup_logger(level=logging.INFO)
    args = argument_parser().parse_args()

    nb_token = args.nautobot_token or credential("nb-token", "token")
    nautobot = pynautobot.api(args.nautobot_url, token=nb_token)

    network_result, subnet_result = sync_neutron_to_nautobot(
        nautobot,
        network_id=args.network or None,
        ucvni_group_name=args.ucvni_group,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        logger.info(
            "Dry run complete. %d networks and %d subnets would be synced.",
            network_result.total,
            subnet_result.total,
        )
    else:
        logger.info(
            "Sync complete. Networks: %d/%d, Subnets: %d/%d synced successfully.",
            network_result.succeeded,
            network_result.total,
            subnet_result.succeeded,
            subnet_result.total,
        )

    total_failed = network_result.failed + subnet_result.failed
    if total_failed:
        logger.error("Failed to sync %d resources", total_failed)
        return _EXIT_SYNC_FAILURES

    return _EXIT_SUCCESS
