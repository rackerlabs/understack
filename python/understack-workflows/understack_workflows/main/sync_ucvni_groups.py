import argparse
import logging
from argparse import Namespace
from enum import StrEnum
from urllib.parse import urljoin

import requests
from requests import RequestException
from requests import Session
from requests.auth import AuthBase

from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__, level=logging.INFO)

_EXIT_SUCCESS = 0
_EXIT_API_ERROR = 1
_EXIT_EVENT_UNKNOWN = 2


class SegmentRangeEvent(StrEnum):
    CREATE = "network_segment_range.create.end"
    UPDATE = "network_segment_range.update.end"
    DELETE = "network_segment_range.delete.end"


class TokenAuth(AuthBase):
    def __init__(self, token: str):
        self.token = token

    def __call__(self, request):
        request.headers["Authorization"] = f"Token {self.token}"
        return request


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


def fetch_ucvni_group(session: Session, api_url: str, segment_name: str) -> dict:
    """Fetch UCVNI group details based on the segment name."""
    try:
        response = session.get(f"{api_url}?name={segment_name}")
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            raise ValueError(f"No UCVNI group found for segment: {segment_name}")
        return results[0]
    except requests.RequestException as e:
        logger.error("Error fetching UCVNI group: %s", str(e))
        raise


def get_old_range(
    session: Session,
    nautobot_url: str,
    segment_range_id: str,
) -> str | None:
    url = f"{nautobot_url}/api/extras/notes/{segment_range_id}/"
    try:
        response = session.get(url)
        response.raise_for_status()

        data = response.json()
        return data.get("note")

    except requests.exceptions.RequestException as e:
        logger.error("Error fetching segment range: %s", str(e))
        return None
    except ValueError:
        logger.error("Error: Invalid JSON response from Nautobot API")
        return None


def modify_range(
    action: SegmentRangeEvent,
    new_range: str,
    existing_range: str,
    old_range: str | None = None,
) -> str:
    def remove_subrange(ranges: list[str], range_to_remove: str | None) -> list[str]:
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

    ranges = existing_range.split(",") if existing_range else []

    match action:
        case SegmentRangeEvent.CREATE:
            ranges.append(new_range)

        case SegmentRangeEvent.DELETE:
            ranges = remove_subrange(ranges, old_range)

        case SegmentRangeEvent.UPDATE:
            # Remove old range completely or adjust if overlapping
            ranges = remove_subrange(ranges, old_range)

            # Add the new updated range
            ranges.append(new_range)

    return ",".join(ranges)


def update_ucvni_range(
    session: Session, api_url: str, ucvni_group_id: str, new_range: str
) -> bool:
    try:
        response = session.patch(
            f"{api_url}{ucvni_group_id}/", json={"range": new_range}
        )
        response.raise_for_status()
        logger.info("Successfully updated UCVNI range: %s", response.json())
        return True
    except requests.RequestException as e:
        logger.error("Failed to update range: %s", str(e))
        return False


def manage_notes(
    session: Session,
    nautobot_url: str,
    ucvni_group_api_url: str,
    ucvni_group_id: str,
    segment_range_id: str,
    segment_range: str,
    action: str,
):
    notes_api_url = urljoin(nautobot_url, "api/extras/notes/")
    endpoint = (
        f"{notes_api_url}{segment_range_id}/"
        if action in [SegmentRangeEvent.UPDATE, SegmentRangeEvent.DELETE]
        else f"{ucvni_group_api_url}{ucvni_group_id}/notes/"
    )
    try:
        if action == SegmentRangeEvent.UPDATE:
            response = session.patch(endpoint, json={"note": segment_range})
        elif action == SegmentRangeEvent.DELETE:
            response = session.delete(endpoint)
        else:
            response = session.post(
                endpoint, json={"id": segment_range_id, "note": segment_range}
            )

        response.raise_for_status()
        logger.info(
            "Successfully executed %s on %s. Response: %s",
            action,
            endpoint,
            response.status_code,
        )

    except RequestException as e:
        logger.error("Failed to %s note at %s: %s", action, endpoint, str(e))
        raise


def handle_event(segment_args: Namespace, action: SegmentRangeEvent) -> int:
    nb_token = segment_args.nautobot_token or credential("nb-token", "token")
    nautobot_session = requests.Session()
    nautobot_session.auth = TokenAuth(nb_token)

    ucvni_group_api_url = urljoin(
        segment_args.nautobot_url, "api/plugins/undercloud-vni/ucvni_groups/"
    )
    ucvni_group_details = fetch_ucvni_group(
        nautobot_session, ucvni_group_api_url, segment_args.segment_name
    )

    ucvni_group_id = ucvni_group_details["id"]
    existing_range = ucvni_group_details.get("range", "")
    segment_range = f"{segment_args.segment_min_range}-{segment_args.segment_max_range}"

    old_range = (
        get_old_range(
            session=nautobot_session,
            nautobot_url=segment_args.nautobot_url,
            segment_range_id=segment_args.segment_range_id,
        )
        if action in [SegmentRangeEvent.DELETE, SegmentRangeEvent.UPDATE]
        else None
    )

    new_range = modify_range(
        action=action,
        existing_range=existing_range,
        new_range=segment_range,
        old_range=old_range,
    )

    manage_notes(
        session=nautobot_session,
        ucvni_group_api_url=ucvni_group_api_url,
        nautobot_url=segment_args.nautobot_url,
        ucvni_group_id=ucvni_group_id,
        segment_range_id=segment_args.segment_range_id,
        segment_range=segment_range,
        action=action,
    )

    return (
        _EXIT_SUCCESS
        if update_ucvni_range(
            nautobot_session, ucvni_group_api_url, ucvni_group_id, new_range
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

    return handle_event(segment_args=args, action=event)
