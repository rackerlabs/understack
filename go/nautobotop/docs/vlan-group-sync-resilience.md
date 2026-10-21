# Making Nautobot sync keep going when one item fails

## Overview

The `nautobotop` operator syncs several Nautobot resource types (vlan groups, vlans,
locations, devices, prefixes, and so on) from Kubernetes ConfigMaps into Nautobot.
Right now the sync stops at the first item Nautobot rejects. When that happens, the
rest of that resource type and everything that syncs after it are skipped for that run.

A few things worth knowing up front:

- When Nautobot rejects a single item, it's usually because the data needs a fix by
  hand, not because the operator is broken. So the goal is to let the sync move past it
  and make it easy to see, not to hide it.
- Desired state comes from Kubernetes ConfigMaps referenced by one cluster-scoped
  `Nautobot` CR (group `sync.rax.io`, `v1alpha1`). Resource types sync in an order based
  on their `dependsOn` links, so a failure early on (like `vlanGroup`) holds up the
  types that come later (`vlan`, `namespace`, `device`, `prefix`, `cluster`, and so on).
- This keeps the single `Nautobot` CRD and the existing ordering. It does not add a
  separate CRD per resource type.
- The same stop-on-first-error pattern shows up in all 18 sync services, so the change
  is written once as a shared helper and then reused.

## An example failure and the fix

Here's the issue that prompted this, and what the sync does today versus after the
change.

### The failure as seen today

The operator went to apply a list of VLAN groups and Nautobot rejected one of them:

```text
UpdateVlanGroup failed to update id 78d8fe0f-6bdd-4ad7-ad51-317d27cfdf70 model n11-21-network
  error 400 Bad Request
  response_body {"range":["VLAN group range may not be re-sized due to existing VLANs (IDs: 4010)."]}

ERROR failed to sync resource {"resource": "vlanGroup",
  "error": "failed to sync vlan groups: failed to update vlan group n11-21-network: 400 Bad Request"}
```

Note: the `400` is expected here. Nautobot won't shrink a VLAN group range while a VLAN
(ID `4010`) is still in the old range. Someone needs to move or remove that VLAN. The
trouble is how much the single rejection holds up, not the rejection itself.

### Why one item stops everything

There are two places where the sync returns on the first error.

The per-type loop in `internal/nautobot/sync/vlanGroup.go` returns on the first item:

```go
for _, vg := range vlanGroups.VlanGroup {
    if err := s.syncSingleVlanGroup(ctx, vg); err != nil {
        return err // skips every remaining vlan group + the prune step
    }
}
```

The reconcile loop in `internal/controller/nautobot_controller.go` returns on the first
resource type:

```go
if err := res.syncFunc(ctx, nautobotClient, dataMap); err != nil {
    return ctrl.Result{}, err // stops the whole reconcile
}
```

So the one rejected VLAN group:

1. Skips every VLAN group listed after it, plus the cleanup step that removes stale ones.
2. Skips every resource type that syncs later, since `vlanGroup` runs early.
3. Leaves nothing lasting to look at: `Status.NautobotStatusReport` is only saved when
   the run finishes cleanly, so the only record is the operator log.

### The fix: skip the bad item, keep going, make it easy to spot

Sort errors into two kinds, carry on past the ones a human needs to fix, and show the
failure in status and in a metric.

- Sort each error into a *data error* (a per-item Nautobot 4xx — skip it and note it) or
  an *infrastructure error* (auth, 5xx, client/cache setup — still stop, so
  controller-runtime backs off and retries).
- Carry on past data errors in each `SyncAll` (collect them with `errors.Join`) and in
  the reconcile loop across resource types. A type that had item failures does not
  update its `SyncHash`, so it's tried again next run; a clean type does update it.
- Note the failure in `Status`, publish a per-resource failure count, and alert on it.

With the change, the same input finishes the run instead of stopping: the other VLAN
groups and the later types sync, and the one bad item shows up in status.

```shell
$ kubectl get nautobot nautobot-prod -o yaml
...
status:
  ready: true
  message: "sync completed with 1 item failure across 1 resource"
  nautobotStatusReport:
    UpdateVlanGroup:
    - 'failed to update n11-21-network: 400 Bad Request: range: VLAN group range may
      not be re-sized due to existing VLANs (IDs: 4010).'
```

The failure is also published so Alertmanager can notify until the data is fixed:

```text
nautobotop_sync_item_failures{nautobot="nautobot-prod",resource="vlanGroup"} 1
```

Once someone moves VLAN `4010` out of the way, the next run applies the range change,
clears the report entry, and the count drops back to `0`.

### Why not a separate CRD per resource type

One option we looked at was splitting the single `Nautobot` CR into a CRD per resource
type — a `VlanGroup` CRD, a `Vlan` CRD, and so on — so each one reconciles on its own
and a bad item only affects its own object. We decided against it for now:

- It doesn't actually solve this problem on its own. A list of VLAN groups still comes
  from one ConfigMap and is applied in a loop, so we'd still need the per-item handling
  from this change. Separate CRDs would be extra work on top, not instead.
- We'd lose the ordering we get for free today. The types sync in a `dependsOn` order
  (vlans need their vlan group, prefixes need their namespace, and so on) that lives in
  one place. Splitting into separate CRDs means rebuilding that ordering across
  controllers.
- It's a lot more surface area: ~18 new CRDs, controllers, and RBAC rules to define and
  keep in step, versus one shared helper.
- The desired state is bulk data in ConfigMaps, which doesn't map cleanly to one CRD per
  item anyway.

Separate CRDs might still make sense later if we want to manage these objects
one-by-one for other reasons, but it's a bigger change and not needed to stop one bad
item from holding up the rest.

## Task map

The work is split into the GitHub issues below.

### 1. Sort sync errors into data vs infrastructure

**Labels:** `area/nautobotop`, `kind/enhancement`, `refactor`
**Depends on:** none

**Background.** A per-item Nautobot `400 Bad Request` is handled the same as an auth/5xx
failure. The first is a data problem to note and skip; the second should stop and back
off.

**Scope.**
- Add an error type/sentinel that separates a **data error** (per-item, not worth
  retrying, Nautobot 4xx) from an **infrastructure error** (auth, 5xx, client/cache
  setup).
- Add a helper that sorts an error from the generated nautobot client + HTTP response by
  status code.
- Unit tests: 400/404/409 → data; 401/403/500/timeout/transport → infra.

**Acceptance criteria.**
- One exported helper for sorting errors.
- No change to the reconcile/sync loops yet.

### 2. Add an item-loop helper for SyncAll

**Labels:** `area/nautobotop`, `kind/enhancement`, `refactor`
**Depends on:** #1

**Background.** Every `SyncAll` in `internal/nautobot/sync/*.go` loops over items and
returns on the first failure. We want one shared way to carry on past data errors and
collect what failed.

**Scope.**
- Add a helper (e.g. `syncItems`) in `internal/nautobot/sync/helpers.go` that loops over
  items, calls a per-item sync func, notes-and-continues on a data error, stops on an
  infrastructure error, and returns the collected per-item failures plus any stopping
  infra error.
- Unit tests: all-success; one data error (continues, cleanup still runs); one infra
  error (stops); mixed.

**Acceptance criteria.**
- Helper has tests and is ready to use.

### 3. Use per-item handling in the VLAN group sync (first example)

**Labels:** `area/nautobotop`, `kind/bug`, `kind/enhancement`
**Depends on:** #1, #2

**Background.** The case from the logs: `n11-21-network` returns `400` and holds up every
other VLAN group plus all the later resource types.

**Scope.**
- Update `VlanGroupSync.SyncAll` (`internal/nautobot/sync/vlanGroup.go`) to use the #2
  helper: carry on past per-item data errors, still run `deleteObsoleteVlanGroups`, stop
  only on infrastructure errors.
- Note per-item failures (item name + response body reason).

**Acceptance criteria.**
- With one VLAN group failing on a 400, the rest are applied and the failure is noted.
- An auth/5xx failure still stops.
- A test covers the `n11-21-network` case and checks the other items succeed.

### 4. Carry on across resource types; only update SyncHash on success

**Labels:** `area/nautobotop`, `kind/bug`, `kind/enhancement`
**Depends on:** #2 (helped by #3)

**Background.** The reconcile loop (`internal/controller/nautobot_controller.go`, ~line
174) returns on the first resource type that fails, which holds up the later types.

**Scope.**
- Carry on to the next resource type when a type reports only per-item data failures;
  still return early on an infrastructure error.
- Only update `SetSyncHash(res.name, ...)` for a resource type that finished cleanly.

**Acceptance criteria.**
- A data failure in an early type (vlanGroup) no longer holds up the later types.
- A type with failures is tried again next run; a clean type isn't re-synced for no
  reason.
- Infrastructure errors still return from `Reconcile` so backoff still works.

### 5. Always save status + report, even on a partial failure

**Labels:** `area/nautobotop`, `kind/bug`, `observability`
**Depends on:** #4

**Background.** `Status.NautobotStatusReport` is only saved on a clean run, so when the
run stops the only record is the log. Operators should be able to see the failing item
from `kubectl get nautobot -o yaml`.

**Scope.**
- Save `Status` (report, `Message`, `Ready`, `LastSyncedAt`) even when some items failed.
- Add a per-resource failure summary to `NautobotStatus` (e.g. `map[resource]failureCount`
  and/or conditions), separate from the free-text report.
- Set `Message` to say the run was partial (e.g. "sync completed with N item failures
  across M resources").
- Regenerate manifests (`make manifests`) and deepcopy (`make generate`).

**Acceptance criteria.**
- After a partial-failure run, `kubectl get nautobot -o yaml` shows which resource(s) and
  item(s) failed and why.
- Status is saved on both the partial-failure and infra-error paths.

### 6. Publish a Prometheus count of per-resource item failures

**Labels:** `area/nautobotop`, `observability`, `kind/enhancement`
**Depends on:** #5

**Background.** The operator uses the default controller-runtime metrics server with no
custom metrics. Alertmanager needs a number to watch.

**Scope.**
- Add a gauge, e.g. `nautobotop_sync_item_failures{nautobot="<cr>",resource="<type>"}`,
  set from the per-resource failure counts from #4/#5 each run.
- Clear the gauge for a resource when it syncs cleanly so a recovery shows up.
- Note the metric name/labels in `go/nautobotop/docs/`.

**Acceptance criteria.**
- Metric is scrapeable and reflects the current per-type failure count.
- A clean run drops it to 0.

### 7. Add a PrometheusRule for failures that stick around

**Labels:** `area/nautobotop`, `observability`, `kind/enhancement`
**Depends on:** #6

**Background.** Closes the loop so on-call gets notified to fix the data (like the
`n11-21-network` range).

**Scope.**
- Add a `PrometheusRule` that alerts when `nautobotop_sync_item_failures > 0` for longer
  than one sync interval, labelled by `resource`, with a note pointing at
  `Status.NautobotStatusReport`.
- Ship it with the operator's deploy manifests/chart, only when prometheus-operator is
  present.

**Acceptance criteria.**
- `promtool`/lint passes on the rule.
- Alert fires on a failure that sticks around and clears when the data is fixed.

### 8. Apply per-item handling to the remaining flat sync services

**Depends on:** #3, #4

**Background.** #3 shows the pattern on vlan groups. The tasks below apply the same
`syncItems` helper to every remaining flat-list `SyncAll`. Each one is self-contained
and can be picked up independently. See `vlanGroup.go` / `vlanGroup_test.go` as the
reference implementation.

**Acceptance criteria (all tasks below).**
- Carries on past per-item data errors (Nautobot 4xx); stops on infra errors.
- `deleteObsolete*` still runs after the apply loop even when some items failed.
- Per-item failures are reported via `client.AddReport` and returned as `PartialSyncError`.
- A one-bad-item test covers the happy path and the single-failure case.

---

#### 8a. `cluster` — `internal/nautobot/sync/cluster.go`

- [ ] Wrap loop in `applyClusters(ctx, clusters, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

#### 8b. `clusterGroup` — `internal/nautobot/sync/clusterGroup.go`

- [ ] Wrap loop in `applyClusterGroups(ctx, clusterGroups, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

#### 8c. `clusterType` — `internal/nautobot/sync/clusterType.go`

- [ ] Wrap loop in `applyClusterTypes(ctx, clusterTypes, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

#### 8d. `device` — `internal/nautobot/sync/device.go`

- [ ] Wrap loop in `applyDevices(ctx, devices, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

#### 8e. `devicetype` — `internal/nautobot/sync/devicetype.go`

- [ ] Wrap loop in `applyDeviceTypes(ctx, deviceTypes, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

#### 8f. `namespace` — `internal/nautobot/sync/namespace.go`

- [ ] Wrap loop in `applyNamespaces(ctx, namespaces, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

#### 8g. `prefix` — `internal/nautobot/sync/prefix.go`

- [ ] Wrap loop in `applyPrefixes(ctx, prefixes, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

#### 8h. `rack` — `internal/nautobot/sync/rack.go`

- [ ] Wrap loop in `applyRacks(ctx, racks, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

#### 8i. `rir` — `internal/nautobot/sync/rir.go`

- [ ] Wrap loop in `applyRirs(ctx, rirs, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

#### 8j. `role` — `internal/nautobot/sync/role.go`

- [ ] Wrap loop in `applyRoles(ctx, roles, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

#### 8k. `tenant` — `internal/nautobot/sync/tenant.go`

- [ ] Wrap loop in `applyTenants(ctx, tenants, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

#### 8l. `tenantGroup` — `internal/nautobot/sync/tenantGroup.go`

- [ ] Wrap loop in `applyTenantGroups(ctx, tenantGroups, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

#### 8m. `vlan` — `internal/nautobot/sync/vlan.go`

- [ ] Wrap loop in `applyVlans(ctx, vlans, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

#### 8n. `admin/permissionGroup` — `internal/nautobot/sync/admin/permissionGroup.go`

- [ ] Wrap loop in `applyPermissionGroups(ctx, perms, syncOne, prune)`.
- [ ] Replace manual for-loop with `syncItems`.
- [ ] Add unit test.

---

### 9. Apply per-item handling to the recursive sync services

**Depends on:** #3, #4

**Background.** Three services sync tree-shaped data (parent → children) via recursion.
The `syncItems` helper works on flat slices; these need a small adaptation to collect
failures across recursive calls without breaking the parent-before-child ordering.

**Acceptance criteria (all tasks below).**
- Same as §8: carries on past data errors, stops on infra errors, prune still runs,
  per-item failures reported, one-bad-item test.
- Parent nodes that succeed are applied even when a child fails.

#### 9a. `location` — `internal/nautobot/sync/location.go`

- [ ] Collect errors from `syncLocationRecursive` calls instead of returning on first.
- [ ] Propagate `PartialSyncError` up through `SyncAll`.
- [ ] Add unit test covering a failing child location with a succeeding sibling.

#### 9b. `locationtype` — `internal/nautobot/sync/locationtype.go`

- [ ] Collect errors from `syncLocationTypeRecursive` calls instead of returning on first.
- [ ] Propagate `PartialSyncError` up through `SyncAll`.
- [ ] Add unit test.

#### 9c. `rackGroup` — `internal/nautobot/sync/rackGroup.go`

- [ ] Collect errors from `syncRackGroupRecursive` calls instead of returning on first.
- [ ] Propagate `PartialSyncError` up through `SyncAll`.
- [ ] Add unit test.
