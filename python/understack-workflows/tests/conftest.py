import uuid
from unittest.mock import MagicMock

import openstack
import pytest
from fixture_nautobot_device import FIXTURE_DELL_NAUTOBOT_DEVICE
from pynautobot import __version__ as pynautobot_version

from understack_workflows.nautobot import Nautobot
from understack_workflows.nautobot_device import NautobotDevice


@pytest.fixture
def dell_nautobot_device() -> NautobotDevice:
    return FIXTURE_DELL_NAUTOBOT_DEVICE


@pytest.fixture
def device_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def domain_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def project_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def bmc_username() -> str:
    return "root"


@pytest.fixture
def bmc_password() -> str:
    return "password"


@pytest.fixture
def project_data(domain_id: uuid.UUID, project_id: uuid.UUID):
    return {
        "id": project_id,
        "domain_id": domain_id,
        "name": "test project",
        "description": "this is a test project",
        "enabled": True,
    }


@pytest.fixture
def os_conn(project_data: dict) -> openstack.connection.Connection:
    def _get_project(project_id):
        if project_id == project_data["id"].hex:
            data = {
                **project_data,
                "id": project_id,
                "domain_id": project_data["domain_id"].hex,
            }
        elif project_id == project_data["domain_id"].hex:
            data = {
                **project_data,
                "id": project_data["domain_id"].hex,
                "domain_id": "default",
            }
        else:
            raise openstack.exceptions.NotFoundException
        return openstack.identity.v3.project.Project(**data)

    conn = MagicMock(spec_set=openstack.connection.Connection)
    conn.identity.get_project.side_effect = _get_project
    return conn


@pytest.fixture
def nautobot_url() -> str:
    return "http://127.0.0.1"


@pytest.fixture
def tenant_data(nautobot_url: str, project_data: dict) -> dict:
    project_id = str(project_data["id"])
    project_url = f"{nautobot_url}/api/tenancy/tenants/{project_id}/"
    return {
        "id": project_id,
        "object_type": "tenancy.tenant",
        "display": project_data["name"],
        "url": project_url,
        "natural_slug": f"{project_data['name']}_6fe6",
        "circuit_count": 0,
        "device_count": 0,
        "ipaddress_count": 0,
        "prefix_count": 0,
        "rack_count": 0,
        "virtualmachine_count": 0,
        "vlan_count": 0,
        "vrf_count": 0,
        "name": "project 1",
        "description": project_data["description"],
        "comments": "",
        "tenant_group": {},
        "created": "2024-08-09T14:03:57.772916Z",
        "last_updated": "2024-08-09T14:03:57.772956Z",
        "tags": [],
        "notes_url": f"{project_url}notes",
        "custom_fields": {},
    }


@pytest.fixture
def nautobot(requests_mock, nautobot_url: str, tenant_data: dict) -> Nautobot:
    requests_mock.get(
        f"{nautobot_url}/api/", headers={"API-Version": pynautobot_version}
    )
    requests_mock.get(tenant_data["url"], json=tenant_data)
    requests_mock.delete(tenant_data["url"])
    requests_mock.post(f"{nautobot_url}/api/tenancy/tenants/", json=tenant_data)
    requests_mock.patch(tenant_data["url"], json=tenant_data)

    return Nautobot(nautobot_url, "blah")
