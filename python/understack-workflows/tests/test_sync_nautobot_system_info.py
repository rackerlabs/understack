import pytest

from understack_workflows.main.sync_nautobot_system_info import argument_parser


@pytest.fixture
def fakebot(mocker):
    return mocker.patch("understack_workflows.nautobot.Nautobot", autospec=True)


@pytest.fixture
def mock_creds(mocker):
    mock = mocker.patch("understack_workflows.node_configuration.credential")
    mock.return_value = "ultra-secret credential value"
    return mock


def test_parse_device_name(mock_creds):
    parser = argument_parser(__name__)
    with pytest.raises(SystemExit):
        parser.parse_args(["--device-id", "FOO"])


def test_parse_device_id(device_id, mock_creds):
    parser = argument_parser(__name__)
    args = parser.parse_args(["--device-id", str(device_id)])

    assert args.device_id == device_id
