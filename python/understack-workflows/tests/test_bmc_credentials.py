import pytest

from understack_workflows.bmc_credentials import set_bmc_password


@pytest.fixture
def mock_redfish(mocker):
    mock = mocker.patch("understack_workflows.bmc_credentials._redfish_request")
    mock.return_value = {"AccountService": {"@odata.id": "/testme"}}
    return mock


@pytest.fixture
def mock_success_auth(mocker):
    mock = mocker.patch("understack_workflows.bmc_credentials._verify_auth")
    mock.return_value = "tOkEn", "/path/to/session/1234"
    return mock


@pytest.fixture
def mock_fail_auth(mocker):
    mock = mocker.patch("understack_workflows.bmc_credentials._verify_auth")
    mock.return_value = None
    return mock


def test_set_bmc_password_noop(mock_success_auth, mock_redfish):
    set_bmc_password("1.2.3.4", "qwertyuiop")
    assert mock_redfish.call_count == 1
    mock_redfish.assert_called_with(
        "1.2.3.4", "/path/to/session/1234", "tOkEn", "DELETE"
    )


def test_set_bmc_password_failed(mock_fail_auth, mock_redfish):
    with pytest.raises(Exception):
        set_bmc_password("1.2.3.4", "qwertyuiop")
