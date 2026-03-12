import pytest

from understack_workflows.bmc import AuthException
from understack_workflows.bmc import RedfishRequestError
from understack_workflows.bmc_credentials import set_bmc_password


@pytest.fixture
def mock_sleep(mocker):
    return mocker.patch("understack_workflows.bmc_credentials.sleep", return_value=None)


def test_set_bmc_password_noop(mocker):
    mock_session = mocker.patch("understack_workflows.bmc_credentials.Bmc.session")
    mock_session.return_value.__enter__.return_value = "tOkEn"

    set_bmc_password("1.2.3.4", "qwertyuiop")

    mock_session.assert_called_once_with("qwertyuiop")


def test_set_bmc_password_change(mocker):
    fail_ctx = mocker.MagicMock()
    fail_ctx.__enter__.side_effect = RedfishRequestError("Auth failed")

    success_ctx = mocker.MagicMock()
    success_ctx.__enter__.return_value = "tOkEn"

    mock_bmc = mocker.patch("understack_workflows.bmc_credentials.Bmc")
    mock_instance = mock_bmc.return_value
    mock_instance.session.side_effect = [fail_ctx, success_ctx, success_ctx]

    set_bmc_password("1.2.3.4", "new_pass", old_password="old_pass")

    mock_instance.set_bmc_creds.assert_called_once_with(
        password="new_pass", token="tOkEn"
    )


def test_set_bmc_password_failed(mocker, mock_sleep):
    mock_session = mocker.patch("understack_workflows.bmc_credentials.Bmc.session")
    mock_session.return_value.__enter__.side_effect = RedfishRequestError("Auth failed")

    with pytest.raises(AuthException):
        set_bmc_password("1.2.3.4", "qwertyuiop")

    mock_sleep.assert_called()
