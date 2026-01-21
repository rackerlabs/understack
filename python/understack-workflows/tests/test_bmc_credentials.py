import pytest

from understack_workflows.bmc import AuthException
from understack_workflows.bmc_credentials import set_bmc_password


@pytest.fixture
def mock_getsession(mocker):
    mock = mocker.patch("understack_workflows.bmc_credentials.Bmc.get_session")
    mock.return_value = "tOkEn", "/path/to/session/1234"
    return mock


@pytest.fixture
def mock_sleep(mocker):
    mock = mocker.patch("understack_workflows.bmc_credentials.sleep", return_value=None)
    return mock


@pytest.fixture
def mock_getsession_failed(mocker):
    mock = mocker.patch("understack_workflows.bmc_credentials.Bmc.get_session")
    mock.side_effect = [
        (None, None),
        (None, None),
        (None, None),
        (None, None),
        (None, None),
    ]  # patching 5 requests for session attempts.
    return mock


@pytest.fixture
def mock_close(mocker):
    mock = mocker.patch("understack_workflows.bmc_credentials.Bmc.close_session")
    mock.return_value = None
    return mock


def test_set_bmc_password_noop(mock_getsession, mock_close):
    set_bmc_password("1.2.3.4", "qwertyuiop")
    mock_getsession.assert_called_once()
    mock_close.assert_called_with(session="/path/to/session/1234", token="tOkEn")


def test_set_bmc_password_failed(mock_getsession_failed, mock_sleep):
    with pytest.raises(AuthException):
        set_bmc_password("1.2.3.4", "qwertyuiop")
