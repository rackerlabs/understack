import pytest

from netinit.esxconfig import ESXConfig
from netinit.esxhost import ESXHost
from netinit.network_data import NetworkData


@pytest.fixture
def host_mock(mocker):
    return mocker.Mock(spec=ESXHost)


def test_configure_requested_dns(host_mock, network_data_single):
    ndata = NetworkData(network_data_single)
    ec = ESXConfig(ndata, dry_run=False)
    ec.host = host_mock
    ec.configure_requested_dns()
    print(host_mock.configure_dns.call_args_list)
    host_mock.configure_dns.assert_called_once_with(servers=["8.8.4.4"])


def test_configure_default_route(network_data_single, host_mock):
    ndata = NetworkData(network_data_single)
    ec = ESXConfig(ndata, dry_run=False)
    ec.host = host_mock
    ec.configure_default_route()
    host_mock.configure_default_route.assert_called_once_with("192.168.1.1")


def test_configure_management_interface(network_data_single, host_mock):
    ndata = NetworkData(network_data_single)
    ec = ESXConfig(ndata, dry_run=False)
    ec.host = host_mock
    ec.configure_management_interface()
    host_mock.change_ip.assert_called_once_with("vmk0", "192.168.1.10", "255.255.255.0")


def test_configure_portgroups(network_data_multi, host_mock):
    ndata = NetworkData(network_data_multi)
    ec = ESXConfig(ndata, dry_run=False)
    ec.host = host_mock
    ec.configure_portgroups()
    assert host_mock.portgroup_add.call_count == 3
    assert host_mock.portgroup_set_vlan.call_count == 3
    host_mock.portgroup_set_vlan.assert_called_with(
        portgroup_name="internal_net_vid_444", vlan_id=444
    )
