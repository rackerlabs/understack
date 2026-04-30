---
charts:
- charts/nautobot-job-queues
deploy_overrides:
  helm:
    mode: values
---

# nautobot-job-queues

Global Nautobot reconciliation job for Celery JobQueue records and
selected existing Nautobot Jobs.

This component is rendered by
`charts/argocd-understack/templates/application-nautobot-job-queues.yaml`.
It runs against the global Nautobot API and reconciles runtime state in
Nautobot; it does not deploy Celery workers.

## Deployment Scope

- Cluster scope: global
- Values key: `global.nautobot_job_queues`
- ArgoCD Application template: `charts/argocd-understack/templates/application-nautobot-job-queues.yaml`
- Helm chart: `charts/nautobot-job-queues`

The ArgoCD Application is ordered after global Nautobot and
`nautobot-api-tokens` by sync wave. Nautobot must be reachable, and the
configured token Secret must exist before the reconciliation Job can
complete.

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component in the global deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  nautobot_job_queues:
    enabled: true
```

## Deployment Repo Content

Required deployment repo content:

- `nautobot-job-queues/values.yaml`: Declares the desired JobQueue
  names, existing Jobs to enable, and optional JobQueue assignments.

Example:

```yaml title="$CLUSTER_NAME/nautobot-job-queues/values.yaml"
queues:
  - site1-dc2

jobs:
  enable:
    groupings: []
    names:
      - Backup Configurations
      - Deploy Config Plan (Job Button Receiver)
      - Deploy Config Plans
      - Generate Intended Configurations
      - Perform Configuration Compliance
  queueAssignments:
    - names:
        - Backup Configurations
        - Deploy Config Plan (Job Button Receiver)
        - Deploy Config Plans
        - Generate Intended Configurations
        - Perform Configuration Compliance
      queues:
        - site1-dc2
```

## Managed State

This component creates or updates Nautobot `JobQueue` records declared
under top-level `queues`.

It can also reconcile existing Nautobot `Job` records:

- `jobs.enable.groupings`: Enable all Jobs with matching Nautobot
  groupings.
- `jobs.enable.names`: Enable Jobs with exact Nautobot names.
- `jobs.queueAssignments`: Add allowed JobQueues for matching Jobs.

This chart does not create Nautobot `Job` records. Jobs such as
`Backup Configurations` are registered by installed Nautobot plugins or
Git-backed Job code. If a requested Job is missing, fix plugin or Job
registration first.

## JobQueue Assignments

Each entry under `jobs.queueAssignments` selects Jobs by `names`,
`groupings`, or both, then assigns them to the listed queues:

```yaml
jobs:
  queueAssignments:
    - names:
        - Backup Configurations
      groupings:
        - Network Automation
      queues:
        - default
        - site1-dc2
      includeExistingQueues: true
      override: true
```

Queues listed in `jobs.queueAssignments[].queues` are assignment
targets only. They are not created unless they also appear under
top-level `queues`. This allows assignments to reference existing
Nautobot queues such as `default` without having the chart create them.

`includeExistingQueues` defaults to `true`, which preserves queues
already assigned to the Job and appends the desired queues. Set it to
`false` when the desired list should replace non-default existing
assignments.

`override` defaults to `true`, which sets Nautobot's
`job_queues_override` flag so the API-configured assignments are used.

## API Access

By default the reconciliation Job calls the in-cluster Nautobot service
with the `nautobot-superuser` API token:

```yaml
api:
  url: http://nautobot-default.nautobot.svc.cluster.local
  tokenSecretRef:
    name: nautobot-superuser
    key: apitoken
```

Override these values only when the Nautobot service name or token
Secret differs for the deployment.

## Relationship to Site Workers

The `nautobot-worker` site component deploys Celery workers that listen
on a site-specific queue, usually the site label such as `site1-dc2`.
This global component creates the matching Nautobot `JobQueue` record
and assigns selected Jobs to that queue so Nautobot accepts runs sent to
the site worker.

When starting a Job through the API, pass the target queue, for example:

```json
{
  "data": {},
  "task_queue": "site1-dc2"
}
```

Nautobot validates that the requested queue exists, is allowed for the
Job, and has a running Celery worker.

## Troubleshooting

If reconciliation fails with a missing Job error, the Job has not been
registered in Nautobot yet. Confirm the plugin or Git-backed Job code is
installed and synced, then run Nautobot's registration path again, such
as `nautobot-server migrate --no-input` from a Nautobot pod.

If running a Job returns `"is not a valid choice"` for `task_queue`,
check that `jobs.queueAssignments` includes the Job and target queue,
then rerun the reconciliation Job.

If Nautobot rejects the run because no worker is listening, check the
site `nautobot-worker` Application and confirm its worker pod has
`CELERY_TASK_QUEUES` set to the same queue name.
