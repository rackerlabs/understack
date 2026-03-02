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

import pynautobot

from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.openstack.client import get_openstack_client
from understack_workflows.oslo_event.neutron_network import sync_network_to_nautobot
from understack_workflows.oslo_event.neutron_subnet import sync_subnet_to_nautobot
from understack_workflows.resync import SyncResult
from understack_workflows.resync import get_nautobot_client
from understack_workflows.resync import log_sync_result

logger = logging.getLogger(__name__)


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resync Neutron to Nautobot")
    return parser_nautobot_args(parser)


def sync_neutron_to_nautobot(
    nautobot: pynautobot.api,
) -> tuple[SyncResult, SyncResult]:
    """Sync Neutron networks and subnets to Nautobot."""
    conn = get_openstack_client()

    network_result = SyncResult()
    subnet_result = SyncResult()
    networks = list(conn.network.networks())  # type: ignore[attr-defined]

    network_external_map: dict[str, bool] = {}

    for network in networks:
        network_result.total += 1
        network_external_map[network.id] = network.is_router_external or False

        logger.info("Syncing network: %s (%s)", network.id, network.name)
        if (
            sync_network_to_nautobot(
                nautobot,
                str(network.id),
                network.name,
                str(network.project_id),
                network.provider_segmentation_id,
            )
            != 0
        ):
            network_result.failed += 1
            logger.error("Failed to sync network %s", network.id)

    subnets = list(conn.network.subnets())  # type: ignore[attr-defined]

    for subnet in subnets:
        subnet_result.total += 1

        logger.info("Syncing subnet: %s (%s)", subnet.id, subnet.name)
        is_external = network_external_map.get(subnet.network_id, False)
        if (
            sync_subnet_to_nautobot(
                nautobot,
                str(subnet.id),
                str(subnet.network_id),
                str(subnet.project_id),
                subnet.cidr,
                is_external,
            )
            != 0
        ):
            subnet_result.failed += 1
            logger.error("Failed to sync subnet %s", subnet.id)

    return network_result, subnet_result


def main() -> int:
    setup_logger(level=logging.INFO)
    args = argument_parser().parse_args()

    nautobot = get_nautobot_client(args)
    network_result, subnet_result = sync_neutron_to_nautobot(nautobot)

    exit_code = log_sync_result(network_result, "network")
    exit_code |= log_sync_result(subnet_result, "subnet")
    return exit_code
