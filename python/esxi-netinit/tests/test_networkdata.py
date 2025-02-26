import json
from dataclasses import is_dataclass

from netinit import Link
from netinit import NetworkData
from netinit import Route


def test_links_parsing(network_data_single):
    network_data = NetworkData(network_data_single)
    assert len(network_data.links) == 1

    link = network_data.links[0]
    assert link.ethernet_mac_address == "00:11:22:33:44:55"
    assert link.id == "eth0"
    assert link.mtu == 1500
    assert link.type == "vif"
    assert link.vif_id == "vif-12345"


def test_networks_parsing(network_data_single):
    network_data = NetworkData(network_data_single)
    assert len(network_data.networks) == 1

    network = network_data.networks[0]
    assert network.id == "net0"
    assert network.ip_address == "192.168.1.10"
    assert network.netmask == "255.255.255.0"
    assert network.network_id == "public"
    assert network.link == Link(
        ethernet_mac_address="00:11:22:33:44:55",
        id="eth0",
        mtu=1500,
        type="vif",
        vif_id="vif-12345",
    )

    # Test routes parsing
    assert len(network.routes) == 2
    assert all(is_dataclass(route) for route in network.routes)

    # Test route values
    assert network.routes[0].gateway == "192.168.1.1"
    assert network.routes[1].network == "0.0.0.0"


def test_services_parsing(network_data_single):
    network_data = NetworkData(network_data_single)
    assert len(network_data.services) == 1

    service = network_data.services[0]
    assert is_dataclass(service)
    assert service.address == "8.8.4.4"
    assert service.type == "dns"


def test_route_default_check():
    default_route = Route(gateway="10.0.0.1", netmask="0.0.0.0", network="0.0.0.0")
    non_default_route = Route(
        gateway="192.168.1.1", netmask="255.255.255.0", network="192.168.1.0"
    )

    assert default_route.is_default() is True
    assert non_default_route.is_default() is False


def test_from_json_file(tmp_path, network_data_single):
    # Create temporary JSON file
    file_path = tmp_path / "test.json"
    with open(file_path, "w") as f:
        json.dump(network_data_single, f)

    # Test loading from file
    network_data = NetworkData.from_json_file(file_path)

    # Verify basic structure
    assert len(network_data.links) == 1
    assert len(network_data.networks) == 1
    assert len(network_data.services) == 1

    # Spot check one value
    assert network_data.networks[0].routes[1].is_default() is True


def test_empty_data():
    empty_data = NetworkData({})
    assert len(empty_data.links) == 0
    assert len(empty_data.networks) == 0
    assert len(empty_data.services) == 0
