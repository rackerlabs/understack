from argparse import Namespace
from unittest import mock
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from understack_workflows.main.sync_ucvni_group_range import _EXIT_API_ERROR
from understack_workflows.main.sync_ucvni_group_range import _EXIT_EVENT_UNKNOWN
from understack_workflows.main.sync_ucvni_group_range import _EXIT_SUCCESS
from understack_workflows.main.sync_ucvni_group_range import SegmentRangeEvent
from understack_workflows.main.sync_ucvni_group_range import handle_event
from understack_workflows.main.sync_ucvni_group_range import main
from understack_workflows.main.sync_ucvni_group_range import modify_range


@pytest.mark.parametrize(
    "action,new_range,existing_range,segment_range_note,expected",
    [
        (SegmentRangeEvent.CREATE, "20-30", "", None, "20-30"),
        (SegmentRangeEvent.CREATE, "20-30", "10-15", None, "10-15,20-30"),
        (SegmentRangeEvent.DELETE, "", "10-15,20-30", "20-30", "10-15"),
        (SegmentRangeEvent.DELETE, "", "10-30", "15-25", "10-14,26-30"),
        (SegmentRangeEvent.DELETE, "", "10-15,20-30", "invalid", "10-15,20-30"),
        (SegmentRangeEvent.UPDATE, "40-50", "10-20,30-35", "30-35", "10-20,40-50"),
        (SegmentRangeEvent.UPDATE, "30-35", "10-20,40-50", "40-50", "10-20,30-35"),
        (SegmentRangeEvent.UPDATE, "15-18", "10-20", "12-16", "10-11,17-20,15-18"),
    ],
)
def test_modify_range(action, new_range, existing_range, segment_range_note, expected):
    mock_notes_endpoint = Mock()
    mock_notes_endpoint.get.return_value = Mock(note=segment_range_note)

    result = modify_range(
        action,
        new_range,
        existing_range,
        segment_range_id="segment123",
        notes_endpoint=mock_notes_endpoint,
    )

    result_parts = sorted(result.split(",")) if result else []
    expected_parts = sorted(expected.split(",")) if expected else []

    assert result_parts == expected_parts


@mock.patch(
    "understack_workflows.main.sync_ucvni_group_range.credential",
    return_value="dummy-token",
)
@mock.patch("understack_workflows.main.sync_ucvni_group_range.Nautobot")
def test_handle_event_ucvni_group_not_found(mock_nautobot_class, mock_credential):
    mock_nautobot = Mock()
    mock_ucvni_groups = Mock()
    mock_ucvni_groups.get.return_value = None  # Simulate UCVNI group not found

    mock_nautobot.session.plugins.undercloud_vni.ucvni_groups = mock_ucvni_groups
    mock_nautobot.session.extras.notes = Mock()

    mock_nautobot_class.return_value = mock_nautobot

    segment_args = Namespace(
        nautobot_token=None,
        nautobot_url="http://mocked-nautobot",
        segment_name="fake-segment",
    )
    result = handle_event(segment_args)
    assert result == _EXIT_API_ERROR
    mock_ucvni_groups.get.assert_called_once_with("fake-segment")


@pytest.mark.parametrize(
    "event,handle_event_return,expected_exit_code",
    [
        (SegmentRangeEvent.CREATE, _EXIT_SUCCESS, _EXIT_SUCCESS),
        ("UNKNOWN_EVENT", None, _EXIT_EVENT_UNKNOWN),
    ],
)
@patch("understack_workflows.main.sync_ucvni_group_range.argument_parser")
@patch("understack_workflows.main.sync_ucvni_group_range.logger")
@patch("understack_workflows.main.sync_ucvni_group_range.handle_event")
def test_main(
    mock_handle_event,
    mock_logger,
    mock_argument_parser,
    event,
    handle_event_return,
    expected_exit_code,
):
    mock_args = Namespace(event=event)
    mock_argument_parser.return_value.parse_args.return_value = mock_args

    if event != "UNKNOWN_EVENT":
        mock_handle_event.return_value = handle_event_return

    result = main()

    assert result == expected_exit_code

    if event == "UNKNOWN_EVENT":
        mock_logger.error.assert_called_once_with(
            "Cannot handle event: %s", "UNKNOWN_EVENT"
        )
        mock_handle_event.assert_not_called()
    else:
        mock_handle_event.assert_called_once_with(segment_args=mock_args)
