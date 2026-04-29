# Nautobot Celery Queues

This guide covers how Celery task queues work in the understack
nautobot-worker deployment, how the queue name is derived from the
site name, and how to route jobs to site-specific queues
programmatically.

## How the Queue Name is Set

The ArgoCD Application template for `nautobot-worker` automatically
sets the Celery queue name to match the site label
(`understack.rackspace.com/site`). The relevant section in
`application-nautobot-worker.yaml`:

{% raw %}

```yaml
{{- with index $.Values.appLabels "understack.rackspace.com/site" }}
values: |
  workers:
    default:
      enabled: false
    {{ . }}:
      enabled: true
      taskQueues: {{ . | quote }}
{{- end }}
```

{% endraw %}

For a site label `site-dc`, this renders as:

```yaml
workers:
  default:
    enabled: false
  site-dc:
    enabled: true
    taskQueues: "site-dc"
```

This produces a Deployment named `nautobot-worker-celery-site-dc` with
the label `app.kubernetes.io/component: nautobot-celery-site-dc` and
the environment variable `CELERY_TASK_QUEUES=site-dc`.

The queue name comes from the ArgoCD Application label
`understack.rackspace.com/site`.

### Why workers.default must be disabled

The upstream Nautobot Helm chart defines `workers.default.taskQueues:
"default"` in its own `values.yaml`. The chart's `nautobot.workers`
helper merges worker-specific values on top of the `celery` defaults.
If you only set `celery.taskQueues`, the chart's `workers.default`
overrides it because worker-level values take precedence. Disabling
`workers.default` and creating a new worker key avoids this conflict.

## Nautobot JobQueue Setup

Before any job can be dispatched to a site queue, a `JobQueue` record
must exist in Nautobot's database. Without it, the API rejects the
request with a validation error.

### Create via the UI

Navigate to Jobs > Job Queues > Add and create a queue with:

- Name: `site-dc` (must match the worker's `taskQueues` value)
- Queue Type: `celery`

### Create via the REST API

```bash
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  https://nautobot.example.com/api/extras/job-queues/ \
  --data '{"name": "site-dc", "queue_type": "celery"}'
```

### Create via pynautobot

```python
import pynautobot

nb = pynautobot.api("https://nautobot.example.com", token="your-token")
nb.extras.job_queues.create(name="site-dc", queue_type="celery")
```

### Automate via Ansible

The `ansible/roles/jobs/tasks/main.yml` role enables jobs but does not
currently create JobQueues. You can extend it:

{% raw %}

```yaml
- name: "Ensure site JobQueue exists"
  ansible.builtin.uri:
    url: "{{ nautobot_url }}/api/extras/job-queues/"
    method: POST
    headers:
      Authorization: "Token {{ nautobot_token }}"
    body_format: json
    body:
      name: "{{ site }}"
      queue_type: "celery"
    status_code: [200, 201, 400]
```

{% endraw %}

## Assigning Jobs to Queues

A job must list the queue in its allowed queues before it can be
dispatched there. There are three ways to do this.

### Option 1: In the Job class (code)

Set `task_queues` in the Job's Meta class. This is baked into the
job's source code and applies everywhere the job is installed.

```python
from nautobot.apps.jobs import Job

class SyncSiteConfig(Job):
    class Meta:
        name = "Sync Site Config"
        task_queues = ["site-dc", "default"]
```

### Option 2: Via the Nautobot UI

Navigate to Jobs > Jobs, select the job, click Edit, and add the
desired JobQueue(s) under the Job Queues field. Check "Override
job queues" to use the UI-configured queues instead of the ones
defined in code.

### Option 3: Via the REST API

```bash
curl -X PATCH \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  https://nautobot.example.com/api/extras/jobs/$JOB_ID/ \
  --data '{
    "job_queues": [{"name": "site-dc"}, {"name": "default"}],
    "job_queues_override": true
  }'
```

## Running Jobs on a Specific Queue

### Via pynautobot

```python
import pynautobot

nb = pynautobot.api("https://nautobot.example.com", token="your-token")

job = nb.extras.jobs.get(name="my_app.jobs.SyncSiteConfig")

# Run on the site worker
result = job.run(data={"device": "server-01"}, task_queue="site-dc")
```

The `task_queue` parameter (or `job_queue` -- both are accepted in
Nautobot 2.4+) tells Nautobot to dispatch the Celery task to the
specified queue. The site worker listening on that queue picks it up.

### Via the REST API

```bash
curl -X POST \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  https://nautobot.example.com/api/extras/jobs/$JOB_ID/run/ \
  --data '{
    "data": {"device": "server-01"},
    "task_queue": "site-dc"
  }'
```

### Via the Nautobot UI

When running a job from the web UI, if the job has multiple queues
configured, a dropdown appears allowing you to select the target
queue before clicking "Run Job".

### Default behavior

If `task_queue` is not specified, Nautobot dispatches the job to the
job's `default_job_queue`. If no default is configured, it falls back
to `CELERY_TASK_DEFAULT_QUEUE` (typically `"default"`).

## Validation

Nautobot validates two things before accepting a job run request:

1. The requested queue must be in the job's allowed queues list.
   If not, the API returns:
   `{"task_queue": ["\"site-dc\" is not a valid choice."]}`

2. At least one Celery worker must be actively listening on the
   requested queue. If no worker is found, the API returns a
   `CeleryWorkerNotRunningException`. This check uses Celery's
   `inspect` to count active workers on the queue.

## Verifying Workers are Listening

To confirm a site worker is consuming from the correct queue:

```bash
# Check the CELERY_TASK_QUEUES env var in the running pod
kubectl -n nautobot get deploy nautobot-worker-celery-site-dc \
            -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="CELERY_TASK_QUEUES")].value}'

# Check worker logs for the queue binding
kubectl logs -n nautobot \
  -l app.kubernetes.io/component=nautobot-celery-site-dc \
  --tail=20 | grep "ready"
```

## Multiple Sites

Each site gets its own queue named after its site label. For example:

| Site | Site Label | Queue Name | Deployment |
|---|---|---|---|
| DC1 Staging | dc1-staging | dc1-staging | nautobot-worker-celery-dc1-staging |
| DC1 Prod | dc1-prod | dc1-prod | nautobot-worker-celery-dc1-prod |
| DC2 Prod | dc2-prod | dc2-prod | nautobot-worker-celery-dc2-prod |
| DC3 Prod | dc3-prod | dc3-prod | nautobot-worker-celery-dc3-prod |

Each site's worker only processes tasks from its own queue. The global
Nautobot instance dispatches jobs to the appropriate queue based on the
`task_queue` parameter in the API call.

## Troubleshooting

### "is not a valid choice" when running a job

The job does not have the requested queue in its allowed queues. Either:

- Add the queue to the job's `task_queues` in code, or
- Add the JobQueue to the job via the UI/API with `job_queues_override: true`

### CeleryWorkerNotRunningException

No worker is listening on the requested queue. Check:

- The site's nautobot-worker ArgoCD Application is synced and healthy
- The worker pod is running: `kubectl get pods -n nautobot -l app.kubernetes.io/component=nautobot-celery-<site>`
- The `CELERY_TASK_QUEUES` env var matches the queue name

### Job runs but nothing happens

The job was dispatched to a queue that no worker is consuming. This
can happen if `task_queue` was not specified and the job defaulted to
`"default"`, but the site worker is listening on `"site-dc"`. Always
pass `task_queue` explicitly when targeting a site worker.
