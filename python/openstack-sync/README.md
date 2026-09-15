# openstack-sync

Shell-operator package for OpenStack reconciliation hooks.

Each hook reconciles one Kubernetes CRD into one kind of OpenStack resource. A
plugin supplies only the parts that are specific to its resource; the shared
hook framework supplies the shell-operator entrypoint, binding-context planning,
connection grouping, status updates, finalizers, and prune ordering.

## Layout

```
openstack_sync/
  utils.py                      Kubernetes Secret access + memoised connections
  hooks/
    framework/
      __init__.py               compatibility facade for hook imports
      common.py                 binding-context I/O, CR status patching
      contracts.py              HookConfig, SyncPlugin, SyncPlan, cleanup dataclasses
      config.py                 hook enablement + shell-operator config
      resources.py              CR parsing, identity, credential grouping
      planner.py                binding-context to SyncPlan planning
      finalizers.py             framework finalizer orchestration
      status.py                 CR status patch assembly
      pruning.py                credential-scoped prune execution
      runner.py                 reconcile/prune/finalizer driver
      entrypoint.py             run_hook implementation
    placeholder.py              connectivity probe (no CRs)
    <resource>.py               CRD hook entry point
  plugins/
    common.py                   OpenStack helpers shared by all plugins
    <service>/<resource>/
      config.py                 plugin constants
      client.py                 OpenStack API calls, if needed
      markers.py                ownership markers
      reconcile.py              converge one CR
      prune.py                  delete resources whose CR was removed, if safe
```

`openstack_sync.hooks.framework` is intentionally still the public import
surface for hooks and tests. New hooks should import `HookConfig`, `SyncPlugin`,
`SyncPlan`, `PruneRequest`, `CleanupPolicy`, `hook_inputs`, `run_sync`, and
`run_hook` from `openstack_sync.hooks.framework`, even though the implementation
now lives in the package modules listed above. `HookInputs` remains as a
compatibility alias for `SyncPlan`. That keeps framework-level monkeypatches,
operational tests, and older imports stable while the internals remain free to
move. The package implementation modules should import each other directly, not
import back through the facade.

## What the framework does for you

`run_sync` groups CRs by the credentials in `spec.cloudCredentialsRef`, adds the
framework finalizer to live CRs that need delete cleanup, opens one connection
per credential group, waits for the OpenStack service, reconciles each CR,
patches `Synced`/`Failed` onto the CR status, and then calls the plugin's prune
step. If any reconcile fails, or any CR could not be read at all, it **skips the
prune entirely** - either way the desired state is unknown, so deleting anything
would be unsafe.

Deleting a finalized CR is a two-phase operation. Kubernetes sets
`metadata.deletionTimestamp` and keeps the object listed; the framework routes
that CR to the plugin's prune path instead of reconciling it. When the plugin
uses a finalizer, the framework removes it only after prune finishes
successfully, so a failed prune keeps the CR around for the next run to retry.
This also makes missed delete events recoverable: terminating CRs in the next
snapshot are still treated as pending deletes.

A finalizer left on a CR the plugin no longer uses is always released, even if a
best-effort prune could not connect. Such a finalizer guards no outstanding
cleanup, so holding it back would only wedge the CR in `Terminating` for a step
it does not depend on.

The framework does not add finalizers by default. It adds one only when
`PRUNE=true` and the plugin has a real prune step. A finalizer tells Kubernetes
to keep a deleted CR around until the controller finishes required cleanup. When
`PRUNE=false`, deleting the CR does not delete anything in OpenStack, so there is
no cleanup for Kubernetes to wait for. The framework leaves finalizers off. If
`PRUNE` is turned off later, the next run removes any finalizer that this
framework added earlier.

A CR whose spec does not satisfy the framework's contract is named in the log and
dropped, and the run exits non-zero. The remaining CRs still reconcile: one
unusable object must not stall a whole namespace.

`run_hook` handles the shell-operator calling convention: `--config`, logging,
reading the binding context, and the exit code.

## Adding a plugin

1. **Write the CRD** in `components/openstack-sync-operator/crds/`. Include a
   `status` subresource and a required `spec.cloudCredentialsRef` with
   `secretName` and `cloudName` - the framework relies on both. Put validation
   (`required`, `enum`, `minLength`, `default`) in the schema so the API server
   rejects bad CRs at admission.

   The schema only validates writes, though. A CR stored before you tightened
   the schema is still served as stored, so give optional fields a default and
   fail one CR by name when a required field is missing.

2. **Register it** in `components/openstack-sync-operator/values.yaml`:

   ```yaml
   plugins:
     <resourceName>: false      # opt in per site
   pluginData:
     <resourceName>:
       hook:
         path: /hooks/<resource>.py
         crd: crds/<group>_<plural>.yaml
         envPrefix: <ENV_PREFIX>
         env:
           SYNC_CRONTAB: "0 * * * *"
   ```

   The chart derives `<ENV_PREFIX>_ENABLED`, `_CRD_API_VERSION`, `_CRD_KIND`,
   `_CRD_RESOURCE` and `_STATUS_ENABLED` from the CRD file, and turns each `env`
   key into `<ENV_PREFIX>_<KEY>`. `HookConfig.from_env` reads only the framework
   keys, such as `PRUNE`, `SYNC_CRONTAB`, `READY_RETRIES` and `READY_DELAY`.
   Plugins read custom prefixed env vars directly.

3. **Write the plugin package** under `plugins/<service>/<resource>/`.
   `config.py` and `reconcile.py` are the usual minimum. Add `markers.py` when
   the plugin stamps ownership into OpenStack resources, and `prune.py` only
   when deleting resources after CR removal is safe and implemented.

4. **Write the hook** - subclass `SyncPlugin` and wire it up:

   ```python
   class ResourcePlugin(SyncPlugin):
       noun = "<resource>"

       def wait_for_api(self, conn) -> None: ...

       def reconcile(self, conn, spec, cache) -> list[str]:
           return reconcile_module.sync(conn, spec, cache)

       def prune_resources(self, conn, request: PruneRequest) -> None:
           if self.config.prune:
               prune_module.prune(conn, request.desired_specs,
                                  authoritative_empty=request.authoritative_empty)

   def main() -> int:
       def run(contexts):
           if not hook_enabled(ENV_PREFIX):
               return 0
           config = HookConfig.from_env(ENV_PREFIX, binding_name=BINDING_NAME)
           return run_sync(ResourcePlugin(config), hook_inputs(contexts, config))

       return run_hook(lambda: build_crd_hook_config(ENV_PREFIX, BINDING_NAME), run)
   ```

   `wait_for_api` and `reconcile` are required; `new_cache` and
   `prune_resources` have working defaults. `PruneRequest` carries the
   credential group being pruned, the full desired spec union, and whether an
   empty desired set is authoritative for that credential group. The framework
   installs finalizers only for plugins that have a prune step and have
   `PRUNE=true`, which maps to `CleanupPolicy.FINALIZED_PRUNE`. If a plugin has
   a different cleanup model, override `cleanup_policy()`. For example,
   RouterFlavor returns `CleanupPolicy.BEST_EFFORT_PRUNE` with `PRUNE=false` so
   its non-destructive profile sweep still runs without holding CR deletion on a
   finalizer.

   Existing plugins that override the legacy `prune(conn, desired_specs, *,
   authoritative_empty)` method still work. Existing overrides of
   `should_run_prune()` and `uses_finalizer()` also continue to feed the default
   `cleanup_policy()`.

## Two rules worth knowing

**A CR is an ownership claim.** Every plugin records ownership on the resources
described by its CRs. If the matching OpenStack resource already exists, the
plugin may stamp the ownership marker and reconcile it; after that, the resource
is operator-managed and can be pruned when the CR is removed. Do not create a CR
for a hand-made resource unless transferring it to the operator is intentional.

**Report what you cannot fix.** `reconcile` returns a list of notes. Use it for
state that diverges from the spec but that OpenStack will not let the operator
correct. The resource is still `Synced`, but the notes appear on the CR status
and in the logs so an operator can act. Raise an exception only for an actual
failure.

## Tests

```sh
uvx ruff check openstack_sync/ tests/ 2>&1
uvx ruff format --check openstack_sync/ tests/ 2>&1
uv run pytest
```

`tests/test_framework.py` exercises the driver with a stub plugin and no
OpenStack at all - read it first to understand the contract a plugin gets.
