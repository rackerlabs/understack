from unittest.mock import MagicMock

import pytest

from understack_workflows.bmc import RedfishRequestError
from understack_workflows.bmc_credentials import set_bmc_password


@pytest.fixture
def mock_getsession(mocker):
    mock = mocker.patch("understack_workflows.bmc_credentials.Bmc.get_session")
    mock.return_value = "tOkEn", "/path/to/session/1234"
    return mock


@pytest.fixture
def mock_close(mocker):
    mock = mocker.patch("understack_workflows.bmc_credentials.Bmc.close_session")
    return mock


@pytest.fixture
def mock_fail_auth(mocker):
    mock_response = MagicMock()
    mock_response.status_code = 402
    mock_response.json.return_value = {"message": "Failure"}
    mock = mocker.patch("requests.request", return_value=mock_response)
    return mock


def test_set_bmc_password_noop(mock_getsession, mock_close):
    set_bmc_password("1.2.3.4", "qwertyuiop")
    mock_getsession.assert_called_once()
    mock_close.assert_called_with(session="/path/to/session/1234", token="tOkEn")


def test_set_bmc_password_failed(mock_fail_auth):
    with pytest.raises(RedfishRequestError):
        set_bmc_password("1.2.3.4", "qwertyuiop")
