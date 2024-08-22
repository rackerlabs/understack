import pytest

from understack_workflows.main.sync_nautobot_interfaces import argument_parser


def test_parse_device_name():
    parser = argument_parser(__name__)
    with pytest.raises(SystemExit):
        parser.parse_args(["--device-id", "FOO"])


def test_parse_device_id(device_id):
    parser = argument_parser(__name__)
    args = parser.parse_args(["--device-id", str(device_id)])

    assert args.device_id == device_id
