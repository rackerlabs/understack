from unittest.mock import MagicMock

from flavor_matcher.flavor_spec import FlavorSpec
from novaclient import client as novaclient
import pytest
from nova_flavors.flavor_synchronizer import FlavorSynchronizer


@pytest.fixture
def flavor_synchronizer():
    return FlavorSynchronizer(
        username="test_username",
        password="test_password",
        auth_url="test_auth_url",
    )


@pytest.fixture
def mock_nova_client(mocker):
    mock_nova_client = mocker.patch.object(novaclient, "Client")
    mock_nova_client.return_value = MagicMock()
    return mock_nova_client


@pytest.fixture
def mock_flavor(mocker):
    return mocker.patch.object(FlavorSpec, "__init__", return_value=None)


@pytest.fixture
def flavor():
    return FlavorSpec(
        name="maybeprod.test_flavor",
        memory_gb=1,
        cpu_cores=2,
        drives=[10, 10],
        model="xyz",
        manufacturer="EvilCorp",
        cpu_model="Pentium 60",
        pci=[],
    )


def test_flavor_synchronizer_init(flavor_synchronizer):
    assert flavor_synchronizer.username == "test_username"
    assert flavor_synchronizer.password == "test_password"
    assert flavor_synchronizer.user_domain_name == "service"
    assert flavor_synchronizer.auth_url == "test_auth_url"


def test_flavor_synchronizer_reconcile_new_flavor(
    flavor_synchronizer, mock_nova_client, flavor
):
    mock_nova_client.return_value.flavors.list.return_value = []
    flavor_synchronizer.reconcile([flavor])
    mock_nova_client.return_value.flavors.create.assert_called_once_with(
        flavor.name, flavor.memory_mib, flavor.cpu_cores, min(flavor.drives)
    )


def test_flavor_synchronizer_reconcile_existing_flavor(
    flavor_synchronizer, mock_nova_client, flavor
):
    existing_flavor = MagicMock()
    existing_flavor.name = flavor.name
    existing_flavor.ram = flavor.memory_mib
    existing_flavor.disk = max(flavor.drives)
    existing_flavor.vcpus = flavor.cpu_cores
    mock_nova_client.return_value.flavors.list.return_value = [existing_flavor]
    flavor_synchronizer.reconcile([flavor])
    mock_nova_client.return_value.flavors.create.assert_not_called()


def test_flavor_synchronizer_reconcile_existing_flavor_update_needed(
    flavor_synchronizer, mock_nova_client, flavor
):
    existing_flavor = MagicMock()
    existing_flavor.name = flavor.name
    existing_flavor.ram = flavor.memory_mib + 1
    existing_flavor.disk = max(flavor.drives)
    existing_flavor.vcpus = flavor.cpu_cores
    existing_flavor.delete = MagicMock()
    mock_nova_client.return_value.flavors.list.return_value = [existing_flavor]
    flavor_synchronizer.reconcile([flavor])
    existing_flavor.delete.assert_called_once()
    mock_nova_client.return_value.flavors.create.assert_called_once_with(
        flavor.name, flavor.memory_mib, flavor.cpu_cores, min(flavor.drives)
    )


def test_flavor_synchronizer_create_flavor(
    mock_nova_client, flavor_synchronizer, flavor
):
    mock_create_flavor = mock_nova_client.return_value.flavors.create.return_value
    flavor_synchronizer._create(flavor)
    mock_nova_client.return_value.flavors.create.assert_called_once_with(
        flavor.name, flavor.memory_mib, flavor.cpu_cores, min(flavor.drives)
    )
    mock_create_flavor.set_keys.assert_called_once_with(
        {
            "resources:DISK_GB": 0,
            "resources:MEMORY_MB": 0,
            "resources:VCPU": 0,
            flavor.baremetal_nova_resource_class: 1,
        }
    )
