import oslo_config.cfg as cfg
import pytest

from neutron_understack.ovn_client import OVNClient


@pytest.fixture
def ovn_opts():
    ovn_opts = [cfg.StrOpt("ovn_nb_connection", default="tcp:10.106.146.16:6641")]
    cfg.CONF.register_opts(ovn_opts, group="ovn")


@pytest.fixture
def ovn_client(ovn_opts):
    return OVNClient()


def test_init(ovn_client):
    assert ovn_client.conn is not None
    assert ovn_client.ovn_nb_api is not None


def test_add_localnet_port(ovn_client, mocker):
    ovn_nb_api_mock = mocker.patch.object(ovn_client, "ovn_nb_api")
    ovn_nb_api_mock.lsp_add.return_value = "mocked_lsp_add_result"
    result = ovn_client.add_localnet_port(
        switch_name="switch",
        network_name="network",
        port_name="port",
        tag=123,
        may_exist=True,
    )
    assert result is not None
    ovn_nb_api_mock.lsp_add.assert_called_once_with(
        "switch",
        "port",
        may_exist=True,
        type="localnet",
        parent_name=[],
        tag=123,
        options={"network_name": "network"},
        addresses=["unknown"],
    )


def test_remove_localnet_port(ovn_client, mocker):
    ovn_nb_api_mock = mocker.patch.object(ovn_client, "ovn_nb_api")
    ovn_nb_api_mock.lsp_del.return_value = None
    ovn_client.remove_localnet_port("switch", "port")
    ovn_nb_api_mock.lsp_del.assert_called_once_with("port", "switch")
