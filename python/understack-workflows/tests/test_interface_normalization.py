from understack_workflows.interface_normalization import normalize_interface_name


def test_normalize_interface_name():
    assert normalize_interface_name("Eth1/1") == "Ethernet1/1"
    assert normalize_interface_name("TigerEth1") == "TigerEth1"
    assert normalize_interface_name("e1") == "Ethernet1"
    assert normalize_interface_name("Gig3/1/1") == "GigabitEthernet3/1/1"
    assert normalize_interface_name("gi3/1/1") == "GigabitEthernet3/1/1"
    assert normalize_interface_name("te3/1/1") == "TenGigabitEthernet3/1/1"
