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
    router_flavors.py           NeutronRouterFlavor hook
  plugins/
    common.py                   OpenStack helpers shared by all plugins
    neutron/router_flavors/
      config.py                 plugin constants
      markers.py                ownership markers
      reconcile.py              converge one CR
      prune.py                  delete resources whose CR was removed
```

## What the framework does for you

`run_sync` groups CRs by the credentials in `spec.cloudCredentialsRef`, opens one
connection per credential group, waits for the OpenStack service, reconciles each
CR, patches `Synced`/`Failed` onto the CR status, and then prunes. If any
reconcile fails, or any CR could not be read at all, it **skips the prune
entirely** — either way the desired state is unknown, so deleting anything would
be unsafe.

A CR whose spec does not satisfy the framework's contract is named in the log and
dropped, and the run exits non-zero. The remaining CRs still reconcile: one
unusable object must not stall a whole namespace.

`run_hook` handles the shell-operator calling convention: `--config`, logging,
reading the binding context, and the exit code.

## Adding a plugin

1. **Write the CRD** in `components/openstack-sync-operator/crds/`. Include a
   `status` subresource and a required `spec.cloudCredentialsRef` with
   `secretName` and `cloudName` — the framework relies on both. Put validation
   (`required`, `enum`, `minLength`, `default`) in the schema so the API server
   rejects bad CRs at admission.

   Schema validation is not a guarantee about what a reconcile receives, though.
   Kubernetes validates on write, so a CR admitted before a field became
   required keeps being served by the watch exactly as stored — tightening a CRD
   neither invalidates nor migrates what already exists. Read schema-optional
   fields with a default, and treat a missing schema-required field as a reason
   to fail that one CR loudly and by name, not as impossible.

2. **Register it** in `components/openstack-sync-operator/values.yaml`:

   ```yaml
   plugins:
     myResource: false          # opt in per site
   pluginData:
     myResource:
       hook:
         path: /hooks/my_resource.py
         crd: crds/<group>_<plural>.yaml
         envPrefix: MY_RESOURCE
         env:
           SYNC_CRONTAB: "0 * * * *"
   ```

   The chart derives `MY_RESOURCE_ENABLED`, `_CRD_API_VERSION`, `_CRD_KIND`,
   `_CRD_RESOURCE` and `_STATUS_ENABLED` from the CRD file, and turns each `env`
   key into `MY_RESOURCE_<KEY>`. `HookConfig.from_env` reads only the framework
   keys, such as `PRUNE`, `SYNC_CRONTAB`, `READY_RETRIES` and `READY_DELAY`.
   Plugins read custom prefixed env vars directly.

3. **Write the plugin package** under `plugins/<service>/<resource>/` with the
   same four modules as `router_flavors`: `config.py` (constants), `markers.py`
   (how you record that the operator owns a resource), `reconcile.py`, `prune.py`.

4. **Write the hook** — subclass `SyncPlugin` and wire it up:

   ```python
   class MyResourcePlugin(SyncPlugin):
       noun = "my resource"

       def wait_for_api(self, conn) -> None: ...

       def reconcile(self, conn, spec, cache) -> list[str]:
           return reconcile_module.sync(conn, spec, cache)

       def prune(self, conn, desired_specs, *, authoritative_empty) -> None:
           if self.config.prune:
               prune_module.prune(conn, desired_specs,
                                  authoritative_empty=authoritative_empty)

   def main() -> int:
       def run(contexts):
           if not hook_enabled(ENV_PREFIX):
               return 0
           config = HookConfig.from_env(ENV_PREFIX, binding_name=BINDING_NAME)
           return run_sync(MyResourcePlugin(config), hook_inputs(contexts, config))

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
correct — for example Neutron rejects `update_service_profile` with a 409 while
the profile is bound to any flavor. The resource is still `Synced`, but the notes
appear on the CR status and in the logs so an operator can act. Raise an
exception only for an actual failure.

## Tests

```sh
uvx ruff check openstack_sync/ tests/ 2>&1
uvx ruff format --check openstack_sync/ tests/ 2>&1
uv run pytest
```

`tests/test_framework.py` exercises the driver with a stub plugin and no
OpenStack at all — read it first to understand the contract a plugin gets.
