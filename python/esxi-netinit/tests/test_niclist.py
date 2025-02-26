import pytest

from netinit import NICList


@pytest.fixture
def sample_niclist_data():
    return """Name    PCI Device    Driver   Admin Status  Link Status  Speed  Duplex  MAC Address         MTU  Description
------  ------------  -------  ------------  -----------  -----  ------  -----------------  ----  -----------
vmnic0  0000:c3:00.0  ntg3     Up            Down             0  Half    c4:cb:e1:bf:79:b6  1500  Broadcom Corporation NetXtreme BCM5720 Gigabit Ethernet
vmnic1  0000:c3:00.1  ntg3     Up            Down             0  Half    c4:cb:e1:bf:79:b7  1500  Broadcom Corporation NetXtreme BCM5720 Gigabit Ethernet
vmnic2  0000:c5:00.0  bnxtnet  Up            Up           25000  Full    d4:04:e6:50:3e:9c  1500  Broadcom NetXtreme E-Series Dual-port 25Gb SFP28 Ethernet OCP 3.0 Adapter
vmnic3  0000:c5:00.1  bnxtnet  Up            Up           25000  Full    d4:04:e6:50:3e:9d  1500  Broadcom NetXtreme E-Series Dual-port 25Gb SFP28 Ethernet OCP 3.0 Adapter
vmnic4  0000:c4:00.0  bnxtnet  Up            Up           25000  Full    14:23:f3:f5:21:50  1500  Broadcom BCM57414 NetXtreme-E 10Gb/25Gb RDMA Ethernet Controller
vmnic5  0000:c4:00.1  bnxtnet  Up            Up           25000  Full    14:23:f3:f5:21:51  1500  Broadcom BCM57414 NetXtreme-E 10Gb/25Gb RDMA Ethernet Controller"""


def test_parse_niclist(sample_niclist_data):
    nics = NICList.parse(sample_niclist_data)

    assert len(nics) == 6
    assert nics[0].name == "vmnic0"
    assert nics[0].mac == "c4:cb:e1:bf:79:b6"
    assert nics[0].status == "Up"
    assert nics[0].link == "Down"
    assert nics[2].name == "vmnic2"
    assert nics[2].mac == "d4:04:e6:50:3e:9c"
    assert nics[2].status == "Up"
    assert nics[2].link == "Up"


def test_find_by_mac(sample_niclist_data):
    nics = NICList(sample_niclist_data)

    found = nics.find_by_mac("d4:04:e6:50:3e:9c")

    assert found.name == "vmnic2"
    assert found.mac == "d4:04:e6:50:3e:9c"
