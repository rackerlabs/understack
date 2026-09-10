# OpenStack Sync Operator — Design Notes

This doc explains how the OpenStack Sync Operator works today, what it does well,
and where it could be better. It's just notes and ideas, not a request to change
anything.

## 1. What it is

Even though it's called an operator, it doesn't run a long-lived reconcile loop.
It's a [flant/shell-operator](https://github.com/flant/shell-operator) deployment
(`ghcr.io/flant/shell-operator:v1.20.2`) that runs short-lived Python scripts
whenever a Kubernetes event happens, plus on a timer. Its job is to take
Kubernetes Custom Resources and turn them into OpenStack config (Neutron router
flavors, Neutron segment ranges, Ironic runbooks), so that config can be managed
through GitOps.

It lives in two places:

- `components/openstack-sync-operator/` — a Helm chart with the runtime pieces:
  the shell-operator Deployment, ServiceAccount, RBAC, and the CRDs.
- `python/openstack-sync/` — the Python package (`openstack_sync`) with the hook
  scripts and reconcile logic, baked into the operator image.

The split is on purpose: the chart owns CRDs, RBAC, and the Deployment because
they change alongside the hook code, while the custom resources (the actual data)
are applied separately. Just applying a CR does nothing unless the matching hook
is turned on in the operator values and its script is in the image.

## 2. How it works

### Runtime model

There's no always-running loop or work queue. shell-operator watches the CRDs and
runs a hook script on each `Added` / `Modified` / `Deleted` event, plus a
periodic full resync on a timer (`SYNC_CRONTAB`). Retries are implicit: if a run
fails, it waits for the next event or the next scheduled resync.

### Core framework

The core is `python/openstack-sync/openstack_sync/hooks/framework.py`. Each
resource type is a `SyncPlugin` subclass that provides four things:

- `wait_for_api(conn)` — wait until the OpenStack service is reachable.
- `reconcile(conn, spec, cache)` — bring one CR spec in line with OpenStack, and
  return any notes about things it won't fix on its own.
- `new_cache()` — a scratch cache shared by all CRs using the same credentials.
- `prune(conn, desired_specs, authoritative_empty)` — delete resources whose CR
  is gone (optional; does nothing by default).

`run_sync()` handles the rest: grouping CRs by credentials, opening one OpenStack
connection per group, reconciling each CR and updating its status, and running a
guarded prune at the end.

### Reconcile behavior (per resource)

The reconcile work is real logic, not a simple apply. A few examples:

- **NeutronRouterFlavor** (`plugins/neutron/router_flavors/reconcile.py`):
  find, adopt, or create each service profile by `(driver, meta_info)`, set up the
  flavor, then line up the set of profiles bound to it. It won't update a profile
  that's bound to a flavor (Neutron returns a 409), so it reports that as
  something to fix by hand instead of failing every run.
- **NeutronSegmentRange** (`plugins/neutron/segment_ranges/reconcile.py`):
  find the managed range by its name; create it if missing, or update the fields
  that can change (`minimum`, `maximum`, `shared`, `project_id`). Fields that
  can't change (`network_type`, `physical_network`) make the CR fail clearly if
  they don't match.
- **IronicRunbook**: similar logic against the Ironic baremetal API.

### Ownership model

Instead of Kubernetes owner references or finalizers, it tracks ownership with
**markers** written into the OpenStack resource itself (`meta_info` keys,
description tags). Prune only deletes resources that carry the marker. Resources
without a marker get adopted (the marker is added) before anything can prune them,
and are otherwise left alone.

### Status management

The CRDs have a status subresource with `syncStatus` (Synced/Failed/Unknown),
`lastSyncTime`, `observedGeneration`, `message`, and a standard `conditions[]`
list. Status is written by running `kubectl patch --subresource status` in a
subprocess (`hooks/common.py`).

### Safety details worth noting

The framework handles a few tricky cases carefully:

- **Avoids reconciling itself** (`_status_is_current`): it skips a `Modified`
  event when the CR's `status.observedGeneration` matches `metadata.generation`
  and `syncStatus == "Synced"`, so its own status update doesn't kick off an
  endless loop.
- **Skips no-op status writes**: it doesn't rewrite status when the important
  fields already match, which avoids extra Modified events.
- **Guards prune**: if any CR failed to reconcile or couldn't be read, prune is
  skipped completely, since it can't know the full desired set and might delete
  something it shouldn't.
- **Only prunes on a real delete**: an empty desired set only triggers a delete
  when a CR using those credentials was actually removed, so it can tell a real
  removal apart from a snapshot it couldn't read.
- **Separate queues per hook**: each hook has its own queue, so a slow readiness
  wait in one hook doesn't hold up the others.

## 3. Observations

### What works well

- The shell-operator model is simple and hard to break. Each run is a fresh
  process, so there's no leaked state, no stale cache, and nothing long-lived to
  go wrong.
- The tricky parts are handled thoughtfully: loop avoidance, prune safety,
  reasoning about what each credential can see, and reporting drift on purpose.
- The plugin contract is small and clearly documented. Adding a resource type
  means writing four methods; the framework does the rest.
- Ownership markers are a sensible fit for external resources that can't carry
  Kubernetes owner references.

### Gaps and risks

1. **Missed deletes aren't recovered.** There are no finalizers, so deletion
   relies on catching the live `Deleted` event. If the operator is down when a CR
   is deleted, that event is gone. On restart it sees a snapshot with the CR
   already missing (not a delete), so it never treats that as a real removal and
   the OpenStack resource is left behind.

2. **No retry/backoff on temporary failures.** A failed run isn't retried on a
   backoff. It waits for the next event or scheduled resync, which could be up to
   an hour depending on `SYNC_CRONTAB`. A short OpenStack hiccup can leave a CR
   `Failed` for a while.

3. **Status uses a `kubectl` subprocess.** This starts a process per patch and
   needs the `kubectl` binary in the image, even though the code already uses the
   Python Kubernetes client to read Secrets. `common.py` even has a
   "kubectl not found" branch to handle its absence.

4. **Single replica, no leader election.** `replicaCount: 1` and no HA. That's
   fine for config sync, but together with the missed-delete gap, any downtime is
   a window where deletes get lost.

5. **No per-resource metrics.** Only shell-operator's built-in metrics (port
   9115) and TCP probes are available. There's nothing per-CRD like reconcile
   count, failure count, or drift-note count for dashboards or alerts.

6. **Markers are defined per plugin.** Each plugin rolls its own marker scheme
   (router flavors in `meta_info`, flavors in `description`, runbooks similar).
   There's no shared, versioned marker format, so a new plugin could do it a
   little differently.

## 4. Suggestions

Roughly in order of value. None of these mean dropping shell-operator.

1. **Add finalizers to fix the missed-delete gap.** A finalizer makes deletion
   reliable no matter the operator's uptime, and removes the need to catch the
   live `Deleted` event. This is the most useful change. It does add a step
   (patching `metadata.finalizers`), so it's worth checking the leak actually
   matters for a resource before adding it everywhere.

2. **Switch status writes to the Python Kubernetes client.** The client is
   already a dependency. This drops the per-patch subprocess, removes the
   `kubectl` binary requirement, gives cleaner error handling, and gets rid of the
   "kubectl not found" case.

3. **Add retry/backoff for temporary failures.** shell-operator doesn't do
   per-object requeue timing, but its queue retry settings can be tuned, or
   `SYNC_CRONTAB` shortened, so a temporary failure retries sooner than the next
   full resync. At least document how long a retry actually takes.

4. **Add per-resource metrics.** Reconcile count, failure count, and drift-note
   count per CRD would make the operator easier to watch. shell-operator can
   export hook metrics; surface them in the chart.

5. **Say the single-replica choice out loud.** If missed deletes matter and
   finalizers aren't added, HA on its own doesn't fully fix it (the event is still
   lost during a gap). Writing down that this is single-replica on purpose, and
   why, helps operators reason about the tradeoff.

6. **Make the marker scheme a shared, versioned contract.** A shared marker module
   with one versioned key format keeps adoption and prune rules consistent across
   plugins and easier to check.

## 5. Are the Python hooks necessary?

The way the hooks are packaged (shell-operator running a script) is a choice, not
a requirement. But the logic inside them is needed for what the operator does
today. Things like "find a resource by a composite key, adopt it if it isn't
marked, line up a set of bindings, refuse to update something that can't be
updated safely and report it instead, and prune only what I own" can't be written
as a plain declarative apply. A generic declarative tool would either error every
run on the cases it can't update, or delete resources it doesn't own.

A fully declarative or idempotent-module approach (say an upsert-only tool, or the
OpenStack Ansible collection this repo already uses elsewhere) would only be
simpler if those requirements went away: no adoption, no markers, no picking which
drift to fix, no CR status. As long as those requirements hold, the logic is
imperative no matter the tool, and moving it to a less suitable tool just spreads
it around instead of simplifying it.

### A middle path

The resources aren't all equally complex.

- `NeutronSegmentRange` is close to a plain create-or-update. Its only special
  cases are some cross-field validation and treating unchangeable fields as hard
  errors — both small.
- `NeutronRouterFlavor` really is imperative: it adopts existing profiles, lines
  up a set of bindings, and reports drift it won't fix.

So one reasonable direction is to keep the Python path only for the resources that
genuinely need adoption and drift handling, and let the simple, upsert-shaped ones
go through a more declarative or idempotent path. That shrinks the Python side
without giving up safety where it actually counts.
