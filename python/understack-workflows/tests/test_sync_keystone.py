import uuid
from contextlib import nullcontext

import pytest
from pytest_lazy_fixtures import lf

from understack_workflows.main.sync_keystone import Event
from understack_workflows.main.sync_keystone import argument_parser
from understack_workflows.main.sync_keystone import do_action


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
    nautobot,
    project_id: uuid.UUID,
    domain_id: uuid.UUID,
):
    ret = do_action(os_conn, nautobot, Event.ProjectCreate, project_id)
    os_conn.identity.get_project.assert_any_call(domain_id.hex)
    os_conn.identity.get_project.assert_any_call(project_id.hex)
    assert ret == 0


def test_update_project(
    os_conn,
    nautobot,
    project_id: uuid.UUID,
    domain_id: uuid.UUID,
):
    ret = do_action(os_conn, nautobot, Event.ProjectUpdate, project_id)
    os_conn.identity.get_project.assert_any_call(domain_id.hex)
    os_conn.identity.get_project.assert_any_call(project_id.hex)
    assert ret == 0


def test_delete_project(
    os_conn,
    nautobot,
    project_id: uuid.UUID,
):
    ret = do_action(os_conn, nautobot, Event.ProjectDelete, project_id)
    assert ret == 0
