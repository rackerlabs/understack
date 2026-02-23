import argparse
import json
import logging
import pathlib
import sys
from typing import Any

from understack_workflows.helpers import setup_logger
from understack_workflows.keystone_project_reconciler import ActionType
from understack_workflows.keystone_project_reconciler import KeystoneProject
from understack_workflows.keystone_project_reconciler import NautobotTenant
from understack_workflows.keystone_project_reconciler import ReconcilerConfig
from understack_workflows.keystone_project_reconciler import build_reconcile_plan

logger = logging.getLogger(__name__)


_EXIT_SUCCESS = 0
_EXIT_BLOCKED = 2
_EXIT_INPUT_ERROR = 3


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prototype Nautobot -> Keystone reconcile planner"
    )
    parser.add_argument(
        "--nautobot-tenants-json",
        type=pathlib.Path,
        required=True,
        help="Path to JSON array of Nautobot tenants",
    )
    parser.add_argument(
        "--keystone-projects-json",
        type=pathlib.Path,
        required=True,
        help="Path to JSON array of Keystone projects",
    )
    parser.add_argument(
        "--source-complete",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether this cycle has a complete source index pull",
    )
    parser.add_argument(
        "--max-disable-abs",
        type=int,
        default=10,
        help="Circuit breaker absolute disable threshold",
    )
    parser.add_argument(
        "--max-disable-pct",
        type=float,
        default=0.05,
        help="Circuit breaker disable ratio threshold",
    )
    parser.add_argument(
        "--disabled-control-tag",
        type=str,
        default="disabled",
        help="Nautobot control-only tag used to disable Keystone project",
    )
    parser.add_argument(
        "--conflict-tag",
        type=str,
        default="UNDERSTACK_ID_CONFLICT",
        help="Tag applied to quarantined conflicting Keystone projects",
    )
    parser.add_argument(
        "--excluded-domain",
        action="append",
        default=["service", "infra"],
        help="Domain excluded from disable/quarantine sweep (repeatable)",
    )
    return parser


def _read_json_array(path: pathlib.Path) -> list[dict[str, Any]]:
    try:
        with path.open() as f:
            data = json.load(f)
    except Exception as exc:  # pragma: no cover - covered by main integration path
        raise ValueError(f"failed to read JSON file {path}: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"{path} item #{idx} must be a JSON object")
    return data


def _as_tenant(item: dict[str, Any]) -> NautobotTenant:
    return NautobotTenant(
        id=str(item["id"]),
        name=str(item["name"]),
        tenant_group=(
            str(item["tenant_group"]) if item.get("tenant_group") is not None else None
        ),
        description=str(item.get("description") or ""),
        tags=frozenset(str(tag) for tag in item.get("tags", [])),
    )


def _as_project(item: dict[str, Any]) -> KeystoneProject:
    return KeystoneProject(
        id=str(item["id"]),
        name=str(item["name"]),
        domain=str(item["domain"]),
        description=str(item.get("description") or ""),
        enabled=bool(item.get("enabled", True)),
        tags=frozenset(str(tag) for tag in item.get("tags", [])),
    )


def _serialize_plan(plan_result) -> dict[str, Any]:
    return {
        "source_complete": plan_result.source_complete,
        "blocked": plan_result.blocked,
        "block_reason": plan_result.block_reason,
        "summary": {
            "create": plan_result.count(ActionType.CREATE),
            "update": plan_result.count(ActionType.UPDATE),
            "disable": plan_result.count(ActionType.DISABLE),
            "quarantine": plan_result.count(ActionType.QUARANTINE),
            "validation_errors": len(plan_result.validation_errors),
        },
        "validation_errors": plan_result.validation_errors,
        "actions": [
            {
                "action_type": action.action_type.value,
                "project_id": action.project_id,
                "domain": action.domain,
                "name": action.name,
                "details": action.details,
            }
            for action in plan_result.actions
        ],
    }


def main() -> int:
    setup_logger(level=logging.INFO)
    args = argument_parser().parse_args()

    try:
        tenants_raw = _read_json_array(args.nautobot_tenants_json)
        projects_raw = _read_json_array(args.keystone_projects_json)
        tenants = [_as_tenant(item) for item in tenants_raw]
        projects = [_as_project(item) for item in projects_raw]
    except Exception as exc:
        logger.error("input parsing failed: %s", exc)
        return _EXIT_INPUT_ERROR

    config = ReconcilerConfig(
        excluded_domains=frozenset(args.excluded_domain),
        disabled_control_tag=args.disabled_control_tag,
        conflict_tag=args.conflict_tag,
        max_disable_abs=args.max_disable_abs,
        max_disable_pct=args.max_disable_pct,
    )
    plan = build_reconcile_plan(
        nautobot_tenants=tenants,
        keystone_projects=projects,
        source_complete=args.source_complete,
        config=config,
    )

    print(json.dumps(_serialize_plan(plan), indent=2, sort_keys=True))
    if plan.blocked:
        return _EXIT_BLOCKED
    return _EXIT_SUCCESS


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
