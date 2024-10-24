import os

import pytest

from understack_workflows.bmc import bmc_for_ip_address


@pytest.fixture
def mock_creds(mocker):
    mock = mocker.patch("understack_workflows.bmc.credential")
    mock.return_value = "ultra-secret credential value"
    return mock


def test_bmc_for_ip_address(mock_creds):
    assert os.getenv("BMC_MASTER") is None
    bmc = bmc_for_ip_address("1.2.3.4")
    assert bmc.ip_address == "1.2.3.4"
    assert bmc.url() == "https://1.2.3.4"
    assert bmc.username == "root"
    assert bmc.password == "1MlzcjJ7bnICKp98wrdx"
