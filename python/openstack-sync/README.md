# openstack-sync

Shell-operator package for OpenStack reconciliation hooks.

Each hook reconciles one Kubernetes CRD into one kind of OpenStack resource. The
generic machinery lives in `openstack_sync/hooks/framework.py`; a plugin supplies
only the parts that are specific to its resource.

## Layout

```
openstack_sync/
  utils.py                      Kubernetes Secret access + memoised connections
  hooks/
    common.py                   binding-context I/O, CR status patching
    framework.py                HookConfig, SyncPlugin, run_sync(), run_hook()
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

## What the framework does for you

`run_sync` groups CRs by the credentials in `spec.cloudCredentialsRef`, opens one
connection per credential group, waits for the OpenStack service, reconciles each
CR, patches `Synced`/`Failed` onto the CR status, and then calls the plugin's
prune step, which most plugins gate on `PRUNE`.

How much of that prune runs depends on how trustworthy the desired set is:

- **All CRs reconciled.** The full prune: resources a deletion names, plus any
  owned resource the desired set does not name, which catches a CR whose removal
  was never observed.
- **A reconcile failed.** Deleting by absence is withheld, because the failing
  CR's resource would read as unwanted. Deletions still go through: they name
  their resources, and the failing CR is still in the desired set and so still
  protected. The run exits non-zero so shell-operator retries it.
- **A CR could not be read.** No prune at all. The desired set is short by
  however many CRs were dropped, and their resource names are unknown, so they
  cannot be protected from a deletion that happens to name one of them.

A CR whose spec does not satisfy the framework's contract is named in the log and
dropped. The remaining CRs still reconcile: one unusable object must not stall a
whole namespace. The run does **not** exit non-zero for this alone, because the
object is stored that way and would be dropped again on every retry -- and
shell-operator re-runs a failing hook every few seconds while blocking the rest
of its queue, so reporting it as a failure would stop the healthy CRs from
reconciling for as long as the malformed CR exists. Alert on the error log.

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

       def prune(self, conn, desired_specs, *, deleted_specs,
                 sweep_unseen) -> None:
           if self.config.prune:
               prune_module.prune(conn, desired_specs,
                                  deleted_specs=deleted_specs,
                                  sweep_unseen=sweep_unseen)

   def main() -> int:
       def run(contexts):
           if not hook_enabled(ENV_PREFIX):
               return 0
           config = HookConfig.from_env(ENV_PREFIX, binding_name=BINDING_NAME)
           return run_sync(ResourcePlugin(config), hook_inputs(contexts, config))

       return run_hook(lambda: build_crd_hook_config(ENV_PREFIX, BINDING_NAME), run)
   ```

   `wait_for_api` and `reconcile` are required; `new_cache` and `prune` have
   working defaults.

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
