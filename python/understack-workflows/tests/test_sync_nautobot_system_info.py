import pytest

from understack_workflows.main.sync_nautobot_system_info import argument_parser, do_sync
from understack_workflows.models import Systeminfo


@pytest.fixture
def fakebot(mocker):
    return mocker.patch("understack_workflows.nautobot.Nautobot", autospec=True)


def test_parse_device_name():
    parser = argument_parser(__name__)
    with pytest.raises(SystemExit):
        parser.parse_args(["--device-id", "FOO",  "--bmc_username", "root", "--bmc_password", "password"])


def test_parse_device_id(device_id, bmc_username, bmc_password):
    parser = argument_parser(__name__)
    args = parser.parse_args(["--device-id", str(device_id), "--bmc_username", bmc_username,
                              "--bmc_password", bmc_password])

    assert args.device_id == device_id
    assert args.bmc_username == bmc_username
    assert args.bmc_password == bmc_password



