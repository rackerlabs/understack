import argparse
import logging
from argparse import Namespace
from enum import StrEnum
from typing import cast

import requests
from pynautobot.core.endpoint import DetailEndpoint
from pynautobot.core.endpoint import Endpoint
from pynautobot.core.response import Record

from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.nautobot import Nautobot

logger = setup_logger(__name__, level=logging.INFO)

_EXIT_SUCCESS = 0
_EXIT_API_ERROR = 1
_EXIT_EVENT_UNKNOWN = 2


class SegmentRangeEvent(StrEnum):
    CREATE = "network_segment_range.create.end"
    UPDATE = "network_segment_range.update.end"
    DELETE = "network_segment_range.delete.end"


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Handle Network Segment Range Events")
    parser.add_argument(
        "event", type=SegmentRangeEvent, choices=list(SegmentRangeEvent)
    )
    parser.add_argument("segment_name", type=str, help="Segment name")
    parser.add_argument("network_type", type=str, help="Network type")
    parser.add_argument("segment_range_id", type=str, help="Segment range ID")
    parser.add_argument("segment_min_range", type=int, help="Segment minimum range")
    parser.add_argument("segment_max_range", type=int, help="Segment maximum range")
    return parser_nautobot_args(parser)


def _remove_subrange(
    ranges: list[str], segment_range_id: str, notes_endpoint
) -> list[str]:
    range_record: Record = cast(Record, notes_endpoint.get(segment_range_id))
    range_to_remove: str | None = range_record.note

    """Remove sub-range and adjust existing ranges."""
    if not range_to_remove:
        return ranges

    updated_ranges = []
    try:
        remove_start, remove_end = map(int, range_to_remove.split("-"))
    except ValueError:
        return ranges  # Return unchanged if range_to_remove is invalid

    for r in ranges:
        start, end = map(int, r.split("-"))

        # If it's an exact match, remove it
        if start == remove_start and end == remove_end:
            continue

        # If there's no overlap, keep the range
        if end < remove_start or start > remove_end:
            updated_ranges.append(r)
        else:
            # Handle partial overlap by splitting
            if start < remove_start:
                updated_ranges.append(f"{start}-{remove_start - 1}")
            if end > remove_end:
                updated_ranges.append(f"{remove_end + 1}-{end}")

    return updated_ranges


def modify_range(
    action: SegmentRangeEvent,
    new_range: str,
    existing_range: str | None,
    segment_range_id: str,
    notes_endpoint: Endpoint,
) -> str:
    ranges = existing_range.split(",") if existing_range else []

    match action:
        case SegmentRangeEvent.CREATE:
            ranges.append(new_range)

        case SegmentRangeEvent.DELETE:
            ranges = _remove_subrange(
                ranges=ranges,
                segment_range_id=segment_range_id,
                notes_endpoint=notes_endpoint,
            )

        case SegmentRangeEvent.UPDATE:
            # Remove old range completely or adjust if overlapping
            ranges = _remove_subrange(
                ranges,
                segment_range_id=segment_range_id,
                notes_endpoint=notes_endpoint,
            )

            # Add the new updated range
            ranges.append(new_range)

    return ",".join(ranges)


def update_ucvni_range(
    segment_args: Namespace,
    notes_endpoint: Endpoint,
    ucvni_group: Record,
) -> bool:
    action: SegmentRangeEvent = segment_args.event
    requested_range = (
        f"{segment_args.segment_min_range}-{segment_args.segment_max_range}"
    )
    new_range = modify_range(
        action=action,
        existing_range=ucvni_group.range,
        new_range=requested_range,
        segment_range_id=segment_args.segment_range_id,
        notes_endpoint=notes_endpoint,
    )

    is_updated = ucvni_group.update(data={"range": new_range})
    if is_updated:
        capture_segment_range_in_notes(
            ucvni_group_notes_endpoint=ucvni_group.notes,
            notes_endpoint=notes_endpoint,
            segment_range_id=segment_args.segment_range_id,
            segment_range=requested_range,
            action=action,
        )
    return is_updated


def capture_segment_range_in_notes(
    ucvni_group_notes_endpoint: DetailEndpoint,
    notes_endpoint: Endpoint,
    segment_range_id: str,
    segment_range: str,
    action: str,
):
    if action == SegmentRangeEvent.UPDATE:
        notes_endpoint.update(id=segment_range_id, data={"note": segment_range})
    elif action == SegmentRangeEvent.DELETE:
        notes_endpoint.delete([segment_range_id])
    else:
        ucvni_group_notes_endpoint.create(
            {"id": segment_range_id, "note": segment_range}
        )


def handle_event(segment_args: Namespace) -> int:
    nb_token = segment_args.nautobot_token or credential("nb-token", "token")
    try:
        nautobot: Nautobot = Nautobot(
            segment_args.nautobot_url, nb_token, logger=logger
        )
        ucvni_group_endpoint: Endpoint = (
            nautobot.session.plugins.undercloud_vni.ucvni_groups
        )
        notes_endpoint: Endpoint = nautobot.session.extras.notes
    except requests.exceptions.ConnectTimeout as e:
        logger.error("Network error while connecting to Nautobot: %s", str(e))
        return _EXIT_API_ERROR

    ucvni_group: Record = cast(
        Record, ucvni_group_endpoint.get(segment_args.segment_name)
    )
    if ucvni_group is None:
        logger.error("No UCVNI group found for segment %s", {segment_args.segment_name})
        return _EXIT_API_ERROR

    return (
        _EXIT_SUCCESS
        if update_ucvni_range(
            segment_args=segment_args,
            ucvni_group=ucvni_group,
            notes_endpoint=notes_endpoint,
        )
        else _EXIT_API_ERROR
    )


def main() -> int:
    args = argument_parser().parse_args()

    event: SegmentRangeEvent = args.event
    if event not in [
        SegmentRangeEvent.CREATE,
        SegmentRangeEvent.UPDATE,
        SegmentRangeEvent.DELETE,
    ]:
        logger.error("Cannot handle event: %s", event)
        return _EXIT_EVENT_UNKNOWN

    return handle_event(segment_args=args)
