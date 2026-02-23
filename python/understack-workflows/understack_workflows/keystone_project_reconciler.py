"""Prototype planner for Nautobot -> Keystone project reconciliation.

This module intentionally focuses on deterministic plan generation.
Live API/DB apply logic is added in later iterations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ActionType(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DISABLE = "disable"
    QUARANTINE = "quarantine"


@dataclass(frozen=True)
class NautobotTenant:
    id: str
    name: str
    tenant_group: str | None
    description: str
    tags: frozenset[str]


@dataclass(frozen=True)
class KeystoneProject:
    id: str
    name: str
    domain: str
    description: str
    enabled: bool
    tags: frozenset[str]


@dataclass(frozen=True)
class DesiredProject:
    id: str
    domain: str
    name: str
    description: str
    enabled: bool
    tags: frozenset[str]


@dataclass(frozen=True)
class ReconcilerConfig:
    excluded_domains: frozenset[str]
    disabled_control_tag: str
    conflict_tag: str
    max_disable_abs: int
    max_disable_pct: float


@dataclass(frozen=True)
class Action:
    action_type: ActionType
    project_id: str
    domain: str
    name: str
    details: dict[str, str]


@dataclass
class PlanResult:
    source_complete: bool
    blocked: bool
    block_reason: str | None
    actions: list[Action]
    validation_errors: list[str]

    def count(self, action_type: ActionType) -> int:
        return sum(1 for action in self.actions if action.action_type == action_type)


def parse_tenant_project_name(
    tenant_name: str, tenant_group_name: str
) -> tuple[str, str] | None:
    """Parse tenant name format "<domain>:<project>".

    Returns tuple(domain, project_name) on success, otherwise None.
    """
    parts = tenant_name.split(":", 1)
    if len(parts) != 2:
        return None
    domain_from_name, project_name = parts
    if domain_from_name != tenant_group_name:
        return None
    if not project_name or ":" in project_name:
        return None
    return domain_from_name, project_name


def desired_project_from_tenant(
    tenant: NautobotTenant,
    disabled_control_tag: str,
) -> tuple[DesiredProject | None, str | None]:
    if not tenant.tenant_group:
        return None, f"tenant {tenant.id} missing tenant_group"

    parsed = parse_tenant_project_name(tenant.name, tenant.tenant_group)
    if parsed is None:
        return (
            None,
            (
                f"tenant {tenant.id} invalid name format '{tenant.name}', expected "
                f"'{tenant.tenant_group}:<project_name>'"
            ),
        )
    domain, project_name = parsed

    enabled = disabled_control_tag not in tenant.tags
    desired_tags = frozenset(tag for tag in tenant.tags if tag != disabled_control_tag)
    return (
        DesiredProject(
            id=tenant.id,
            domain=domain,
            name=project_name,
            description=tenant.description or "",
            enabled=enabled,
            tags=desired_tags,
        ),
        None,
    )


def _short_id(project_id: str, length: int = 8) -> str:
    cleaned = project_id.replace("-", "")
    return cleaned[:length]


def _should_disable_unknown(
    project: KeystoneProject, managed_domains: set[str]
) -> bool:
    if project.domain not in managed_domains:
        return False
    return project.enabled


def _add_update_actions(
    actions: list[Action], desired: DesiredProject, actual: KeystoneProject
):
    details: dict[str, str] = {}
    if actual.name != desired.name:
        details["name"] = desired.name
    if (actual.description or "") != (desired.description or ""):
        details["description"] = desired.description
    if actual.enabled != desired.enabled:
        details["enabled"] = str(desired.enabled)
    if actual.tags != desired.tags:
        details["tags"] = ",".join(sorted(desired.tags))

    if details:
        actions.append(
            Action(
                action_type=ActionType.UPDATE,
                project_id=desired.id,
                domain=desired.domain,
                name=desired.name,
                details=details,
            )
        )


def _evaluate_breaker(
    actions: list[Action],
    managed_project_count: int,
    max_disable_abs: int,
    max_disable_pct: float,
) -> tuple[bool, str | None]:
    disable_count = sum(
        1
        for action in actions
        if action.action_type in (ActionType.DISABLE, ActionType.QUARANTINE)
    )
    if disable_count > max_disable_abs:
        return (
            True,
            (
                "breaker tripped: disables "
                f"{disable_count} exceed max_disable_abs {max_disable_abs}"
            ),
        )

    if managed_project_count <= 0:
        return False, None

    disable_pct = disable_count / managed_project_count
    if disable_pct > max_disable_pct:
        return (
            True,
            (
                "breaker tripped: disable ratio "
                f"{disable_pct:.3f} exceeds max_disable_pct {max_disable_pct:.3f}"
            ),
        )

    return False, None


def build_reconcile_plan(
    nautobot_tenants: list[NautobotTenant],
    keystone_projects: list[KeystoneProject],
    source_complete: bool,
    config: ReconcilerConfig,
) -> PlanResult:
    if not source_complete:
        return PlanResult(
            source_complete=False,
            blocked=True,
            block_reason="source index incomplete; all writes blocked for this cycle",
            actions=[],
            validation_errors=[],
        )

    actions: list[Action] = []
    validation_errors: list[str] = []
    desired_by_id: dict[str, DesiredProject] = {}
    desired_by_domain_name: dict[tuple[str, str], DesiredProject] = {}

    for tenant in nautobot_tenants:
        desired, error = desired_project_from_tenant(
            tenant, config.disabled_control_tag
        )
        if error:
            validation_errors.append(error)
            continue
        if desired is None:
            # Defensive guard: keep planner deterministic if parser contract changes.
            validation_errors.append(
                f"tenant {tenant.id} produced no desired project and no error"
            )
            continue
        desired_by_id[desired.id] = desired
        desired_by_domain_name[(desired.domain, desired.name)] = desired

    actual_by_id = {project.id: project for project in keystone_projects}
    actual_by_domain_name = {(p.domain, p.name): p for p in keystone_projects}

    managed_domains = {
        desired.domain
        for desired in desired_by_id.values()
        if desired.domain not in config.excluded_domains
    }

    # Create/update path for desired projects.
    for desired in desired_by_id.values():
        actual = actual_by_id.get(desired.id)
        if actual:
            if actual.domain != desired.domain:
                validation_errors.append(
                    f"domain immutability violation for {desired.id}: "
                    f"keystone={actual.domain} nautobot={desired.domain}"
                )
                continue
            _add_update_actions(actions, desired, actual)
            continue

        conflict = actual_by_domain_name.get((desired.domain, desired.name))
        if conflict and conflict.id != desired.id:
            quarantine_name = f"{conflict.name}:INVALID:{_short_id(conflict.id)}"
            quarantine_tags = sorted(set(conflict.tags) | {config.conflict_tag})
            actions.append(
                Action(
                    action_type=ActionType.QUARANTINE,
                    project_id=conflict.id,
                    domain=conflict.domain,
                    name=quarantine_name,
                    details={
                        "enabled": "False",
                        "tags": ",".join(quarantine_tags),
                    },
                )
            )

        actions.append(
            Action(
                action_type=ActionType.CREATE,
                project_id=desired.id,
                domain=desired.domain,
                name=desired.name,
                details={
                    "description": desired.description,
                    "enabled": str(desired.enabled),
                    "tags": ",".join(sorted(desired.tags)),
                },
            )
        )

    # Disable unknown projects in managed domains.
    for actual in keystone_projects:
        if actual.id in desired_by_id:
            continue
        if not _should_disable_unknown(actual, managed_domains):
            continue
        actions.append(
            Action(
                action_type=ActionType.DISABLE,
                project_id=actual.id,
                domain=actual.domain,
                name=actual.name,
                details={"enabled": "False"},
            )
        )

    breaker_blocked, breaker_reason = _evaluate_breaker(
        actions=actions,
        managed_project_count=len(desired_by_id),
        max_disable_abs=config.max_disable_abs,
        max_disable_pct=config.max_disable_pct,
    )

    return PlanResult(
        source_complete=True,
        blocked=breaker_blocked,
        block_reason=breaker_reason,
        actions=actions,
        validation_errors=validation_errors,
    )
