import os

import pytest

from understack_workflows.bmc import Bmc
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


def test_manager_attributes_path_uses_advertised_idrac10_resource(mocker):
    bmc = Bmc("10.46.104.6")
    bmc._manager_path = "/redfish/v1/Managers/iDRAC.Embedded.1"
    mocker.patch.object(
        bmc,
        "redfish_request",
        return_value={
            "Links": {
                "Oem": {
                    "Dell": {
                        "DellAttributes": [
                            {
                                "@odata.id": (
                                    "/redfish/v1/Managers/iDRAC.Embedded.1/Oem/Dell/"
                                    "DellAttributes/System.Embedded.1"
                                )
                            },
                            {
                                "@odata.id": (
                                    "/redfish/v1/Managers/iDRAC.Embedded.1/Oem/Dell/"
                                    "DellAttributes/iDRAC.Embedded.1"
                                )
                            },
                        ]
                    }
                }
            }
        },
    )

    assert bmc.manager_attributes_path == (
        "/redfish/v1/Managers/iDRAC.Embedded.1/Oem/Dell/DellAttributes/iDRAC.Embedded.1"
    )


def test_manager_attributes_path_falls_back_to_idrac9_resource(mocker):
    bmc = Bmc("10.46.104.6")
    bmc._manager_path = "/redfish/v1/Managers/iDRAC.Embedded.1"
    mocker.patch.object(bmc, "redfish_request", return_value={})

    assert bmc.manager_attributes_path == (
        "/redfish/v1/Managers/iDRAC.Embedded.1/Attributes"
    )
