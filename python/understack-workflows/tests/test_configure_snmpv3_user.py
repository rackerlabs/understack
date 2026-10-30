from unittest.mock import Mock
from unittest.mock import call

import pytest
from ironicclient.common.apiclient import exceptions
from tenacity import stop_after_attempt
from tenacity import wait_none

from understack_workflows.main import configure_snmpv3_user as cli


def test_conflict_retries_the_same_request_without_lifecycle_calls():
    client = Mock()
    client.client.node.vendor_passthru.side_effect = [
        exceptions.Conflict("Node is busy"),
        {"configured": True},
    ]
    # Tenacity adds retry_with at runtime but does not expose it in its types.
    configure = cli.configure_snmpv3_user.retry_with(  # pyright: ignore[reportFunctionMemberAccess]
        wait=wait_none(), stop=stop_after_attempt(2)
    )

    configure(client, "node-uuid", 5)

    request = call.client.node.vendor_passthru(
        "node-uuid", "configure_snmpv3_user", args={"slot": 5}, http_method="POST"
    )
    assert client.mock_calls == [request, request]


@pytest.mark.parametrize("error", [exceptions.BadRequest, exceptions.Forbidden])
def test_permanent_errors_are_not_retried(error):
    client = Mock()
    client.client.node.vendor_passthru.side_effect = error("Cannot configure")

    with pytest.raises(error):
        cli.configure_snmpv3_user(client, "node-uuid", 5)

    client.client.node.vendor_passthru.assert_called_once()


def test_busy_node_eventually_fails():
    client = Mock()
    client.client.node.vendor_passthru.side_effect = exceptions.Conflict("Busy")
    # Tenacity adds retry_with at runtime but does not expose it in its types.
    configure = cli.configure_snmpv3_user.retry_with(  # pyright: ignore[reportFunctionMemberAccess]
        wait=wait_none(), stop=stop_after_attempt(2)
    )

    with pytest.raises(exceptions.Conflict):
        configure(client, "node-uuid", 5)

    assert client.client.node.vendor_passthru.call_count == 2


def test_main_resolves_node_and_uses_monitoring_slot(mocker):
    mocker.patch("sys.argv", ["configure-snmpv3-user", "--node", "Dell-ABC1234"])
    client = mocker.patch.object(cli, "IronicClient").return_value
    client.get_node.return_value.uuid = "node-uuid"
    configure = mocker.patch.object(cli, "configure_snmpv3_user")

    cli.main()

    configure.assert_called_once_with(client, "node-uuid", 5)


@pytest.mark.parametrize("slot", ["2", "17", "invalid"])
def test_invalid_slot_is_rejected(slot):
    with pytest.raises(SystemExit):
        cli.argument_parser().parse_args(["--node", "node-uuid", "--slot", slot])
