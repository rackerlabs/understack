from understack_workflows.keystone_project_reconciler import ActionType
from understack_workflows.keystone_project_reconciler import KeystoneProject
from understack_workflows.keystone_project_reconciler import NautobotTenant
from understack_workflows.keystone_project_reconciler import ReconcilerConfig
from understack_workflows.keystone_project_reconciler import build_reconcile_plan
from understack_workflows.keystone_project_reconciler import parse_tenant_project_name


def _config(**kwargs) -> ReconcilerConfig:
    base = ReconcilerConfig(
        excluded_domains=frozenset({"service", "infra"}),
        disabled_control_tag="disabled",
        conflict_tag="UNDERSTACK_ID_CONFLICT",
        max_disable_abs=10,
        max_disable_pct=0.05,
    )
    values = {**base.__dict__, **kwargs}
    return ReconcilerConfig(**values)


def test_parse_tenant_project_name_valid():
    assert parse_tenant_project_name("default:project-a", "default") == (
        "default",
        "project-a",
    )


def test_parse_tenant_project_name_invalid_prefix():
    assert parse_tenant_project_name("default:project-a", "sandbox") is None


def test_build_plan_blocks_writes_when_source_incomplete():
    plan = build_reconcile_plan(
        nautobot_tenants=[],
        keystone_projects=[],
        source_complete=False,
        config=_config(),
    )
    assert plan.blocked is True
    assert plan.actions == []


def test_build_plan_create_for_missing_project():
    tenant = NautobotTenant(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        name="default:alpha",
        tenant_group="default",
        description="alpha project",
        tags=frozenset({"UNDERSTACK_SVM"}),
    )
    plan = build_reconcile_plan(
        nautobot_tenants=[tenant],
        keystone_projects=[],
        source_complete=True,
        config=_config(max_disable_pct=1.0),
    )
    assert plan.blocked is False
    assert plan.count(ActionType.CREATE) == 1
    create_action = plan.actions[0]
    assert create_action.details["enabled"] == "True"
    assert create_action.details["tags"] == "UNDERSTACK_SVM"


def test_build_plan_disabled_tag_becomes_enabled_false():
    tenant = NautobotTenant(
        id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        name="default:beta",
        tenant_group="default",
        description="beta project",
        tags=frozenset({"disabled", "UNDERSTACK_SVM"}),
    )
    plan = build_reconcile_plan(
        nautobot_tenants=[tenant],
        keystone_projects=[],
        source_complete=True,
        config=_config(max_disable_pct=1.0),
    )
    create_action = plan.actions[0]
    assert create_action.details["enabled"] == "False"
    assert create_action.details["tags"] == "UNDERSTACK_SVM"


def test_build_plan_conflict_quarantine_and_create():
    tenant = NautobotTenant(
        id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        name="default:gamma",
        tenant_group="default",
        description="gamma project",
        tags=frozenset(),
    )
    conflicting_project = KeystoneProject(
        id="dddddddd-dddd-dddd-dddd-dddddddddddd",
        domain="default",
        name="gamma",
        description="old",
        enabled=True,
        tags=frozenset({"foo"}),
    )
    plan = build_reconcile_plan(
        nautobot_tenants=[tenant],
        keystone_projects=[conflicting_project],
        source_complete=True,
        config=_config(max_disable_pct=1.0),
    )
    assert plan.count(ActionType.QUARANTINE) == 1
    assert plan.count(ActionType.CREATE) == 1
    quarantine = [a for a in plan.actions if a.action_type == ActionType.QUARANTINE][0]
    assert quarantine.details["enabled"] == "False"
    assert "UNDERSTACK_ID_CONFLICT" in quarantine.details["tags"]


def test_build_plan_disable_unknown_in_managed_domain():
    tenant = NautobotTenant(
        id="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        name="default:delta",
        tenant_group="default",
        description="delta project",
        tags=frozenset(),
    )
    unknown = KeystoneProject(
        id="ffffffff-ffff-ffff-ffff-ffffffffffff",
        domain="default",
        name="orphan",
        description="old",
        enabled=True,
        tags=frozenset(),
    )
    plan = build_reconcile_plan(
        nautobot_tenants=[tenant],
        keystone_projects=[unknown],
        source_complete=True,
        config=_config(max_disable_pct=1.0),
    )
    assert plan.count(ActionType.DISABLE) == 1


def test_build_plan_excluded_domain_not_disabled():
    # No desired projects, but service domain should be excluded from disable.
    service_project = KeystoneProject(
        id="11111111-1111-1111-1111-111111111111",
        domain="service",
        name="svc",
        description="service project",
        enabled=True,
        tags=frozenset(),
    )
    plan = build_reconcile_plan(
        nautobot_tenants=[],
        keystone_projects=[service_project],
        source_complete=True,
        config=_config(max_disable_pct=1.0),
    )
    assert plan.count(ActionType.DISABLE) == 0


def test_build_plan_breaker_blocks_all_writes():
    tenant = NautobotTenant(
        id="22222222-2222-2222-2222-222222222222",
        name="default:epsilon",
        tenant_group="default",
        description="epsilon project",
        tags=frozenset(),
    )
    unknown1 = KeystoneProject(
        id="33333333-3333-3333-3333-333333333333",
        domain="default",
        name="unknown1",
        description="",
        enabled=True,
        tags=frozenset(),
    )
    unknown2 = KeystoneProject(
        id="44444444-4444-4444-4444-444444444444",
        domain="default",
        name="unknown2",
        description="",
        enabled=True,
        tags=frozenset(),
    )
    plan = build_reconcile_plan(
        nautobot_tenants=[tenant],
        keystone_projects=[unknown1, unknown2],
        source_complete=True,
        config=_config(max_disable_abs=1, max_disable_pct=1.0),
    )
    assert plan.blocked is True
    assert plan.block_reason is not None
