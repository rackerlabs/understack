import pytest
from unittest.mock import MagicMock
from understack_workflows.bmc_credentials import set_bmc_password

@pytest.fixture
def mock_redfish(mocker):
    mock = mocker.patch("understack_workflows.bmc_credentials._redfish_request")
    mock.return_value = {"AccountService": {"@odata.id": "/testme"}}
    return mock

def test_set_bmc_password(mock_redfish):
    logger = MagicMock()
    set_bmc_password("1.2.3.4", "qwertyuiop")
    mock_redfish.assert_any_call("1.2.3.4", "/redfish/v1", "root", "qwertyuiop")
    mock_redfish.assert_any_call("1.2.3.4", "/testme", "root", "qwertyuiop")
