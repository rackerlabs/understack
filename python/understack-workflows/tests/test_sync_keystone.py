import uuid
from contextlib import nullcontext

import pytest
from pytest_lazy_fixtures import lf

from understack_workflows.domain import DefaultDomain
from understack_workflows.main.sync_keystone import Event
from understack_workflows.main.sync_keystone import argument_parser
from understack_workflows.main.sync_keystone import do_action
from understack_workflows.main.sync_keystone import is_valid_domain


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
                "--only-domain",
                lf("domain_id"),
                "identity.project.created",
                lf("project_id"),
            ],
            nullcontext(),
            lf("project_id"),
        ),
        (
            ["--only-domain", "default", "identity.project.created", lf("project_id")],
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


@pytest.mark.parametrize(
    "only_domain,expected",
    [
        (None, True),
        (DefaultDomain(), False),
        (lf("domain_id"), True),
    ],
)
def test_is_valid_domain(os_conn, project_id, only_domain, expected):
    assert is_valid_domain(os_conn, project_id, only_domain) == expected


@pytest.mark.parametrize(
    "only_domain",
    [
        None,
        lf("domain_id"),
        uuid.uuid4(),
    ],
)
def test_create_project(
    os_conn,
    nautobot,
    project_id: uuid.UUID,
    only_domain: uuid.UUID | DefaultDomain | None,
):
    do_action(os_conn, nautobot, Event.ProjectCreate, project_id, only_domain)
    os_conn.identity.get_project.assert_called_with(project_id.hex)


@pytest.mark.parametrize(
    "only_domain",
    [
        None,
        lf("domain_id"),
        uuid.uuid4(),
    ],
)
def test_update_project(
    os_conn,
    nautobot,
    project_id: uuid.UUID,
    only_domain: uuid.UUID | DefaultDomain | None,
):
    do_action(os_conn, nautobot, Event.ProjectUpdate, project_id, only_domain)
    os_conn.identity.get_project.assert_called_with(project_id.hex)


@pytest.mark.parametrize(
    "only_domain",
    [
        None,
        lf("domain_id"),
        uuid.uuid4(),
    ],
)
def test_delete_project(
    os_conn,
    nautobot,
    project_id: uuid.UUID,
    only_domain: uuid.UUID | DefaultDomain | None,
):
    do_action(os_conn, nautobot, Event.ProjectDelete, project_id, only_domain)
