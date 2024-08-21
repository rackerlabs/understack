import pytest

from understack_workflows.main.sync_provision_state import argument_parser
from understack_workflows.main.sync_provision_state import do_action


@pytest.fixture
def fakebot(mocker):
    return mocker.patch("understack_workflows.nautobot.Nautobot", autospec=True)


def test_parse_device_name():
    parser = argument_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--device-id", "FOO"])


def test_parse_device_id(device_id):
    parser = argument_parser()
    args = parser.parse_args(
        ["--device-id", str(device_id), "--provision-state", "active"]
    )

    assert args.device_id == device_id


def test_calls_update_cf(fakebot, device_id):
    do_action(fakebot, device_id, "active")

    fakebot.update_cf.assert_called_once_with(
        device_id, "ironic_provision_state", "active"
    )


def test_updates_device_status(fakebot, device_id):
    do_action(fakebot, device_id, "error")

    fakebot.update_device_status.assert_called_once_with(device_id, "Quarantine")


def test_no_change_irrelevant_state(fakebot, device_id):
    do_action(fakebot, device_id, "servicing")

    fakebot.update_device_status.assert_not_called()


def test_no_change_on_wrong_state(fakebot, device_id):
    with pytest.raises(ValueError):
        do_action(fakebot, device_id, "this-is-made-up")
