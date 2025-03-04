import pytest

from netinit.esxhost import ESXHost


@pytest.fixture
def esx_host(fp):
    fp.register(["/bin/esxcli", fp.any()])
    return ESXHost()


def test_portgroup_add(fp, esx_host):
    esx_host.portgroup_add("mypg")
    assert (
        fp.call_count(
            "/bin/esxcli network vswitch standard portgroup add --portgroup-name mypg --vswitch-name vswitch0"
        )
        == 1
    )


def test_portgroup_set_vlan(fp, esx_host):
    esx_host.portgroup_set_vlan("mypg", 1984)
    assert (
        fp.call_count(
            "/bin/esxcli network vswitch standard portgroup set --portgroup-name mypg --vlan-id 1984"
        )
        == 1
    )


def test_create_vswitch(fp, esx_host):
    esx_host.create_vswitch(name="vSwitch8", ports=512)
    assert (
        fp.call_count(
            "/bin/esxcli network vswitch standard add --ports 512 --vswitch-name vSwitch8"
        )
        == 1
    )


def test_destroy_vswitch(fp, esx_host):
    esx_host.destroy_vswitch(name="vSwitch8")
    assert (
        fp.call_count(
            "/bin/esxcli network vswitch standard remove --vswitch-name vSwitch8"
        )
        == 1
    )


def test_portgroup_remove(fp, esx_host):
    esx_host.portgroup_remove(switch_name="vSwitch20", portgroup_name="Management")
    assert (
        fp.call_count(
            "/bin/esxcli network vswitch standard portgroup remove --portgroup-name Management --vswitch-name vSwitch20"
        )
        == 1
    )


def test_uplink_add(fp, esx_host):
    esx_host.uplink_add(switch_name="vSwitch8", nic="vmnic4")
    assert (
        fp.call_count(
            "/bin/esxcli network vswitch standard uplink add --uplink-name vmnic4 --vswitch-name vSwitch8"
        )
        == 1
    )


def test_vswitch_settings(fp, esx_host):
    esx_host.vswitch_settings(mtu=9000, cdp="listen", name="vSwitch8")
    assert (
        fp.call_count(
            "/bin/esxcli network vswitch standard set --mtu 9000 --cdp-status listen --vswitch-name vSwitch8"
        )
        == 1
    )


def test_vswitch_failover_uplinks_active(fp, esx_host):
    esx_host.vswitch_failover_uplinks(active_uplinks=["vmnic4", "vmnic10"])
    assert fp.call_count(
        "/bin/esxcli network vswitch standard policy failover set --active-uplinks vmnic4,vmnic10 --vswitch-name vSwitch0"
    )


def test_vswitch_failover_uplinks_standby(fp, esx_host):
    esx_host.vswitch_failover_uplinks(standby_uplinks=["vmnic3", "vmnic7"])
    assert fp.call_count(
        "/bin/esxcli network vswitch standard policy failover set --standby-uplinks vmnic3,vmnic7 --vswitch-name vSwitch0"
    )


def test_vswitch_security(fp, esx_host):
    esx_host.vswitch_security(
        allow_forged_transmits="no",
        allow_mac_change="no",
        allow_promiscuous="yes",
        name="vSwitch7",
    )
    assert (
        fp.call_count(
            "/bin/esxcli network vswitch standard policy security set --allow-forged-transmits no --allow-mac-change no --allow-promiscuous yes --vswitch-name vSwitch7"
        )
        == 1
    )


def test_configure_dns(fp, esx_host):
    fp.register(["/bin/esxcli", fp.any()])
    fp.keep_last_process(True)
    esx_host.configure_dns(servers=["8.8.8.8", "4.4.4.4"], search=["example.com"])
    assert fp.call_count("/bin/esxcli network ip dns server add --server 8.8.8.8") == 1
    assert fp.call_count("/bin/esxcli network ip dns server add --server 4.4.4.4") == 1
    assert (
        fp.call_count("/bin/esxcli network ip dns search add --domain example.com") == 1
    )


def test_delete_vmknic(fp, esx_host):
    fp.register(["/bin/esxcfg-vmknic", fp.any()])
    esx_host.delete_vmknic(portgroup_name="ManagementPG")
    assert fp.call_count("/bin/esxcfg-vmknic -d ManagementPG") == 1


def test_add_ip_interface(fp, esx_host):
    esx_host.add_ip_interface(name="vmk1", portgroup_name="VMNet-Mgmt")
    assert (
        fp.call_count(
            "/bin/esxcli network ip interface add --interface-name vmk1 --portgroup-name VMNet-Mgmt"
        )
        == 1
    )
