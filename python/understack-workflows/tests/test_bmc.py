import os

import pytest

from understack_workflows.bmc import bmc_for_ip_address


@pytest.fixture
def mock_creds(mocker):
    mock = mocker.patch("understack_workflows.bmc.credential")
    mock.return_value = "ultra-secret credential value"
    return mock


def test_bmc_for_ip_address(mock_creds, monkeypatch):
    # The credential function above is overridden by the environment variable so
    # make sure it is removed, so we are using the correct test credential and
    # not a production one.
    monkeypatch.delenv("BMC_MASTER", raising=False)
    assert os.getenv("BMC_MASTER") is None

    bmc = bmc_for_ip_address("1.2.3.4")

    assert bmc.ip_address == "1.2.3.4"
    assert bmc.url() == "https://1.2.3.4"
    assert bmc.username == "root"
    assert bmc.password == "1MlzcjJ7bnICKp98wrdx"
