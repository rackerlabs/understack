import uuid
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest
from openstack.connection import Connection
from pytest_lazy_fixtures import lf

from understack_workflows.main.sync_keystone import Event
from understack_workflows.main.sync_keystone import argument_parser
from understack_workflows.main.sync_keystone import do_action
from understack_workflows.main.sync_keystone import handle_project_delete


@pytest.fixture
def mock_pynautobot_api(mocker):
    mock_client = MagicMock(name="MockPynautobotApi")

    mock_devices = MagicMock()
    mock_devices.filter.return_value = []
    mock_devices.update.return_value = True
    mock_client.dcim.devices = mock_devices

    mock_tenants = MagicMock()
    mock_tenants.get.return_value = None
    mock_tenants.delete.return_value = True
    mock_client.tenancy.tenants = mock_tenants

    mocker.patch(
        "understack_workflows.main.sync_keystone.pynautobot.api",
        return_value=mock_client,
    )

    return mock_client


@pytest.mark.parametrize(
    "arg_list,context,expected_id",
    [
        (["identity.project.created", ""], pytest.raises(SystemExit), None),
        (["identity.project.created", "http"], pytest.raises(SystemExit), None),
        (
            ["identity.project.created", lf("project_id")],
            nullcontext(),
            lf("project_id"),
        ),
        (
            [
                "identity.project.created",
                lf("project_id"),
            ],
            nullcontext(),
            lf("project_id"),
        ),
        (
            ["identity.project.created", lf("project_id")],
            nullcontext(),
            lf("project_id"),
        ),
    ],
)
def test_parse_object_id(arg_list, context, expected_id):
    parser = argument_parser()
    with context:
        args = parser.parse_args([str(arg) for arg in arg_list])

        assert args.object == expected_id


def test_create_project(
    os_conn,
    mock_pynautobot_api,
    project_id: uuid.UUID,
    domain_id: uuid.UUID,
):
    ret = do_action(os_conn, mock_pynautobot_api, Event.ProjectCreate, project_id)
    os_conn.identity.get_project.assert_any_call(project_id.hex)
    os_conn.identity.get_domain.assert_any_call(domain_id.hex)
    assert ret == 0


def test_update_project(
    os_conn,
    mock_pynautobot_api,
    project_id: uuid.UUID,
    domain_id: uuid.UUID,
):
    ret = do_action(os_conn, mock_pynautobot_api, Event.ProjectUpdate, project_id)
    os_conn.identity.get_project.assert_any_call(project_id.hex)
    os_conn.identity.get_domain.assert_any_call(domain_id.hex)
    assert ret == 0


def test_update_project_domain_skipped(
    os_conn,
    mock_pynautobot_api,
    domain_id: uuid.UUID,
):
    """Test that domains are skipped during update events."""
    ret = do_action(os_conn, mock_pynautobot_api, Event.ProjectUpdate, domain_id)
    # Should fetch the project to check if it's a domain
    os_conn.identity.get_project.assert_called_once_with(domain_id.hex)
    # Should NOT call get_domain or create/update tenant since it's a domain
    os_conn.identity.get_domain.assert_not_called()
    mock_pynautobot_api.tenancy.tenants.get.assert_not_called()
    mock_pynautobot_api.tenancy.tenants.create.assert_not_called()
    assert ret == 0


def test_delete_project(
    os_conn,
    mock_pynautobot_api,
    project_id: uuid.UUID,
):
    ret = do_action(os_conn, mock_pynautobot_api, Event.ProjectDelete, project_id)
    assert ret == 0


@pytest.mark.parametrize(
    "tenant_exists, expect_delete_call, expect_unmap_call",
    [
        (False, False, False),  # Tenant does NOT exist
        (True, True, True),  # Tenant exists
    ],
)
def test_handle_project_delete(
    mocker, mock_pynautobot_api, tenant_exists, expect_delete_call, expect_unmap_call
):
    project_id = uuid.uuid4()

    tenant_obj = MagicMock()
    mock_pynautobot_api.tenancy.tenants.get.return_value = (
        tenant_obj if tenant_exists else None
    )

    mock_unmap_devices = mocker.patch(
        "understack_workflows.main.sync_keystone._unmap_tenant_from_devices"
    )
    conn_mock: Connection = MagicMock(spec=Connection)
    ret = handle_project_delete(conn_mock, mock_pynautobot_api, project_id)

    assert ret == 0
    mock_pynautobot_api.tenancy.tenants.get.assert_called_once_with(id=project_id)

    if tenant_exists:
        mock_unmap_devices.assert_called_once_with(
            tenant_id=project_id, nautobot=mock_pynautobot_api
        )
        tenant_obj.delete.assert_called_once()
    else:
        mock_unmap_devices.assert_not_called()
        tenant_obj.delete.assert_not_called()
