import pytest

from netinit import ESXConfig
from netinit import NetworkData


@pytest.fixture
def empty_ec(fp):
    fp.register(["/bin/esxcli", fp.any()])
    return ESXConfig(NetworkData({}))

def test_configure_default_route(fp, network_data_single):
    fp.register(["/bin/esxcli", fp.any()])
    ndata = NetworkData(network_data_single)
    ec = ESXConfig(ndata, dry_run=False)
    ec.configure_default_route()
    assert fp.call_count("/bin/esxcli network ip route ipv4 add -g 192.168.1.1 -n default") == 1

def test_configure_management_interface(fp, network_data_single):
    fp.register(["/bin/esxcli", fp.any()])
    ndata = NetworkData(network_data_single)
    ec = ESXConfig(ndata, dry_run=False)
    ec.configure_management_interface()
    assert fp.call_count("/bin/esxcli network ip interface ipv4 set -i vmk0 -I 192.168.1.10 -N 255.255.255.0 -t static") == 1

def test_portgroup_add(fp, empty_ec):
    empty_ec.portgroup_add("mypg")
    assert fp.call_count("/bin/esxcli network vswitch standard portgroup add --portgroup-name mypg --vswitch-name vswitch0") == 1

def test_portgroup_set_vlan(fp, empty_ec):
    empty_ec.portgroup_set_vlan("mypg", 1984)
    assert fp.call_count("/bin/esxcli network vswitch standard portgroup set --portgroup-name mypg --vlan-id 1984") == 1

def test_configure_portgroups(fp, mocker, network_data_multi) :
    fp.register(["/bin/esxcli", fp.any()])
    ndata = NetworkData(network_data_multi)
    ec = ESXConfig(ndata, dry_run=False)
    pgadd_mock = mocker.patch.object(ec, "portgroup_add")
    pgset_mock = mocker.patch.object(ec, "portgroup_set_vlan")
    ec.configure_portgroups()
    assert pgadd_mock.call_count == 3
    assert pgset_mock.call_count == 3
    pgset_mock.assert_called_with(portgroup_name="internal_net_vid_444", vlan_id=444)

def test_create_vswitch(fp, empty_ec):
    empty_ec.create_vswitch(name="vSwitch8", ports=512)
    assert fp.call_count("/bin/esxcli network vswitch standard add --ports 512 --vswitch-name vSwitch8") == 1

def test_uplink_add(fp, empty_ec):
    empty_ec.uplink_add(switch_name="vSwitch8", nic="vmnic4")
    assert fp.call_count("/bin/esxcli network vswitch standard uplink add --uplink-name vmnic4 --vswitch-name vSwitch8") == 1

def test_vswitch_settings(fp, empty_ec):
    empty_ec.vswitch_settings(mtu=9000, cdp="listen", name="vSwitch8")
    assert fp.call_count("/bin/esxcli network vswitch standard set --mtu 9000 --cdp-status listen --vswitch-name vSwitch8") == 1

def test_vswitch_failover_uplinks_active(fp, empty_ec):
    empty_ec.vswitch_failover_uplinks(active_uplinks=["vmnic4", "vmnic10"])
    assert fp.call_count("/bin/esxcli network vswitch standard policy failover set --active-uplinks vmnic4,vmnic10 --vswitch-name vSwitch0")

def test_vswitch_failover_uplinks_standby(fp, empty_ec):
    empty_ec.vswitch_failover_uplinks(standby_uplinks=["vmnic3", "vmnic7"])
    assert fp.call_count("/bin/esxcli network vswitch standard policy failover set --standby-uplinks vmnic3,vmnic7 --vswitch-name vSwitch0")

def test_vswitch_security(fp, empty_ec):
    empty_ec.vswitch_security(allow_forged_transmits="no", allow_mac_change="no", allow_promiscuous="yes", name="vSwitch7")
    assert fp.call_count("/bin/esxcli network vswitch standard policy security set --allow-forged-transmits no --allow-mac-change no --allow-promiscuous yes --vswitch-name vSwitch7") == 1

def test_configure_dns(fp, empty_ec):
    fp.register(["/bin/esxcli", fp.any()])
    fp.keep_last_process(True)
    empty_ec.configure_dns(servers=['8.8.8.8', '4.4.4.4'], search=["example.com"])
    assert fp.call_count("/bin/esxcli network ip dns server add --server 8.8.8.8") == 1
    assert fp.call_count("/bin/esxcli network ip dns server add --server 4.4.4.4") == 1
    assert fp.call_count("/bin/esxcli network ip dns search add --domain example.com") == 1

def test_configure_requested_dns(fp, network_data_single):
    fp.register(["/bin/esxcli", fp.any()])
    ndata = NetworkData(network_data_single)
    ec = ESXConfig(ndata, dry_run=False)
    ec.configure_requested_dns()
    assert fp.call_count("/bin/esxcli network ip dns server add --server 8.8.4.4") == 1
