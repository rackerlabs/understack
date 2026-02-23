# Keystone Project Reconciler

This page describes the planned operator model for the site-local Keystone
project reconciler.

## Overview

Each site runs one reconciler worker that:

- Pulls desired project state from global Nautobot
- Reconciles local Keystone projects to match desired state
- Creates projects with fixed UUIDs using Keystone DB/library path
- Updates project metadata/state/tags using Keystone API
- Disables (not deletes) stale projects
- Applies circuit breaker protections before writes

## Deployment Model

- Workload type: Kubernetes `Deployment`
- Replicas: `1` per site
- Startup behavior: full reconcile before loop
- Loop cadence:
    - incremental reconcile every 30 seconds
    - lightweight full ID index every 60 seconds
    - full drift reconcile every 10 minutes

## Rollout Sequence

1. Disable Keystone -> Nautobot project sync.
2. Deploy reconciler in planner/audit mode first.
3. Validate diff outputs, validation errors, and breaker behavior.
4. Enable enforcement per managed domain.
5. Monitor SLO and breaker metrics during ramp-up.

## Required Inputs

Use separate secrets for each credential set.

### Secrets

- Nautobot API credentials
    - token
    - URL
- Keystone API credentials
    - auth URL
    - username/password or equivalent
    - domain/project scope
- Keystone DB credentials
    - DSN or host/port/user/password/db name

### Config

Recommended runtime configuration:

```yaml
reconcile:
  incremental_interval_seconds: 30
  index_interval_seconds: 60
  full_interval_seconds: 600
  startup_full_reconcile: true

domains:
  excluded:
    - service
    - infra

tags:
  disabled_control_tag: disabled
  conflict_tag: UNDERSTACK_ID_CONFLICT

breaker:
  max_disable_abs: 10
  max_disable_pct: 0.05
  block_all_writes: true
  override_secret_name: understack-keystone-reconcile-override
  override_expiry_key: expires_at
```

## Circuit Breaker Behavior

Each cycle uses a plan-first workflow:

1. Build planned actions.
2. Evaluate thresholds.
3. If breaker trips, apply no writes.
4. Emit logs and metrics for alerting.

Trip conditions:

- planned disables > `max_disable_abs`
- or planned disables / managed projects > `max_disable_pct`

Manual override:

- Override is per-site and time-limited via secret expiry.
- Expired override must not bypass breaker.

Completeness guard:

- If the source index pull is incomplete for a cycle, that cycle performs no
  writes and alerts.

## Conflict Quarantine Runbook

When `(domain, project_name)` exists with the wrong UUID:

1. Disable the conflicting project.
2. Rename to `<old_name>:INVALID:<short-project-id>`.
3. Add `UNDERSTACK_ID_CONFLICT` tag.
4. Alert for manual remediation.

Quarantined projects are manual-only and are not auto-recovered.

## Day-2 Operations

### Verify Worker Health

- Pod is running and stable
- Last successful reconcile metric is updating
- Breaker trip count is not increasing unexpectedly

### Force Full Reconcile

- Restart reconciler Pod (startup full reconcile runs automatically)

### Enable Temporary Breaker Override

Create/update override secret with a near-term expiry timestamp. Remove or let
expire after change window.

### Investigate Data Validation Alerts

Common causes:

- Tenant name not in `<tenant_group>:<project_name>` format
- Tenant name prefix does not match Tenant Group name
- Tenant missing Tenant Group
- Domain immutability violation for existing project UUID
- Keystone tag update rejection (offending tag skipped)

## Metrics and Alerting

Emit OpenTelemetry metrics and alert on:

- reconcile cycle failures
- breaker trips
- conflict quarantine actions
- validation skips
- stale last-success timestamp
- tag-skip events caused by Keystone tag update rejections

Recommended metric dimensions:

- `site`
- `action_type`
- `result`
- `domain`

## Notes

- Automation never hard-deletes Keystone projects.
- Removed or disabled Nautobot tenants result in Keystone disable operations.
- Tag management is exact from Nautobot except `disabled`, which is control-only.
- If Keystone rejects a specific tag update, the worker skips only that tag,
  continues project reconciliation, and alerts via logs/metrics.
