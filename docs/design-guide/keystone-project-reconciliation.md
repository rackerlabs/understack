# Keystone Project Reconciliation

This document describes the planned design for synchronizing OpenStack Keystone
projects across all site clusters from a single source of truth in Nautobot.

## Problem

UnderStack deploys independent Keystone instances per site for resiliency.
Keystone project UUIDs must be consistent across all sites, but Keystone API
project creation does not let operators provide a project UUID.

## Goals

- Use Nautobot as the source of truth for project identity and metadata.
- Keep project UUIDs identical across all sites.
- Reconcile changes within 120 seconds.
- Never hard-delete Keystone projects from automation.
- Scale from tens to thousands of projects.

## Non-Goals

- Managing Keystone domains dynamically. Domains are pre-created.
- Using per-project GitOps commits or per-project Kubernetes resources.

## Source of Truth Mapping

- Nautobot `tenant.id` -> Keystone `project.id` (authoritative UUID)
- Nautobot `tenant_group.name` -> Keystone `domain.name` (exact match)
- Nautobot `tenant.name` format -> `<tenant_group>:<project_name>`
    - `:` is reserved as delimiter
    - `:` is not allowed in the project-name segment
    - prefix before `:` must exactly match `tenant_group.name`
- Nautobot `tenant.description` -> Keystone `project.description`
- Nautobot tags -> Keystone project tags (exact managed set), except:
    - `disabled` is control-only and does not get written as a Keystone tag

Special tags:

- `disabled` (lowercase) on Nautobot tenant means Keystone `enabled=false`
- `UNDERSTACK_SVM` is managed exactly from Nautobot tags
- `UNDERSTACK_ID_CONFLICT` is used for quarantined Keystone projects

## Reconciler Topology

Run one site-local reconciler process per site as a Kubernetes `Deployment`
with a single replica.

Reasons:

- 30-second cadence is required for SLO and is not a good fit for cron syntax.
- Long-running worker avoids Pod churn.
- Site-local pull remains operational during partial partition events.

Each site reconciler can call global Nautobot API directly.

## Reconciliation Model

The reconciler uses a pull loop with three cadences:

- Every 30s: incremental Nautobot fetch using in-memory `updated_since`
  watermark.
- Every 60s: lightweight full tenant index fetch (`id`, `name`,
  `tenant_group`, `tags`) to detect deletes quickly.
- Every 10m: full drift reconciliation.

On startup, run a full reconciliation before entering the loop.

## Write Paths

Hybrid Keystone write strategy:

- Create with fixed UUID: Keystone library/DB path (direct DB write path).
- Update operations (rename, description, enabled state, tag set):
  Keystone API (`openstacksdk`).

## Domain and Project Behavior

- All Tenant Groups are treated as managed Keystone domains.
- Managed domain exclusions: `service`, `infra` are excluded from
  disable/quarantine sweeps.
- Domain is immutable for a given project UUID.
    - If Nautobot moves a tenant to another Tenant Group, reconciler alerts and
      skips automatic migration.

## Delete and Disable Semantics

- If tenant has `disabled` tag, disable matching Keystone project.
- If tenant is removed from Nautobot, disable matching Keystone project.
- If a disabled tenant becomes active again, re-enable Keystone project.
- No automated Keystone project hard-delete.

## Drift Handling

Within managed domains (except excluded domains), Keystone projects not present
in Nautobot desired state are disabled by reconciliation.

If a whole Tenant Group disappears from Nautobot, reconciler only alerts and
does not bulk-disable that domain.

## Conflict Quarantine

If target `(domain, project_name)` already exists in Keystone with a different
UUID than Nautobot:

1. Disable the conflicting Keystone project.
2. Rename to deterministic quarantine name:
   `<old_name>:INVALID:<short-project-id>`.
3. Add tag `UNDERSTACK_ID_CONFLICT`.
4. Mark for manual remediation only (no auto-recovery).

## Circuit Breaker

Each cycle is `plan -> guard -> apply`:

1. Build full action plan first (`create`, `update`, `disable`, `quarantine`).
2. Evaluate breaker.
3. If tripped, block all writes for that cycle and alert.

Initial thresholds:

- `disable_count > 10` OR
- `disable_count / managed_project_count > 0.05`

Manual override:

- Per-site override secret with expiry timestamp.
- Override allows temporary breaker bypass for controlled runs.

## Observability

Emit logs and OpenTelemetry metrics for:

- Cycle duration
- Planned/applied action counts by action type
- Breaker trips
- Last successful reconcile timestamp
- Alert-worthy data validation failures (name format, missing tenant group,
  domain immutability violations, conflicts)
- Tag enforcement rejections (per-tag skip events)

## Security and Credentials

Credentials are provided via multiple Kubernetes secrets:

- Global Nautobot API URL/token
- Keystone API credentials
- Keystone DB credentials for fixed UUID creation path

Use dedicated least-privilege credentials where possible.

## Proposed Implementation Phases

1. Implement reconciler command in `python/understack-workflows`.
2. Add plan/apply engine, conflict quarantine, and circuit breaker.
3. Add OpenTelemetry metrics and structured logging.
4. Add Kubernetes `Deployment` and config/secret wiring in site workflows.
5. Add test coverage for mapping, conflicts, deletes, breaker, and tag
   behavior.

## Implementation Plan

### Phase 0: Cutover Preparation

- Disable existing Keystone -> Nautobot project synchronization.
- Confirm Nautobot tenant data quality for:
    - required Tenant Group
    - `<tenant_group>:<project_name>` naming
    - tag usage (`disabled`, `UNDERSTACK_SVM`)

### Phase 1: Planner Prototype

- Build deterministic `plan -> guard` engine:
    - desired-state mapping from Nautobot tenants
    - conflict quarantine planning
    - disable planning for stale projects in managed domains
    - source-completeness gate (block writes if source index incomplete)
    - circuit breaker thresholds and block-all-writes behavior
- Add unit tests for planner behavior.

### Phase 2: Reconciler Worker Skeleton

- Add long-running site-local worker process (`Deployment`, replicas=1).
- Startup full reconcile, then 30s incremental + 60s index + 10m full loop.
- Emit logs and OpenTelemetry metrics for cycle state and guard outcomes.

### Phase 3: Apply Engine

- Implement write paths:
    - fixed UUID project create via Keystone library/DB
    - update/disable/tag via Keystone API
- Add ordered apply execution and error handling with partial-failure
  reporting.

### Phase 4: Rollout Safety

- Add audit-only domain mode for staged rollout.
- Enable domain-by-domain enforcement after clean audits.
- Add timed per-site manual breaker override.

### Phase 5: Production Hardening

- Add integration tests (API + DB path).
- Add SLO-aligned alerting and dashboards.
- Add runbooks for conflict remediation and override usage.

## Tag Rejection Handling

Keystone project tags are expected to be freeform, but if a tag update is
rejected at API time:

- skip only the offending tag(s) for that project
- continue reconciliation for the rest of that project state
- emit alerts and OpenTelemetry metrics for operator follow-up
