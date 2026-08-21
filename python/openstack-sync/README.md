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
reconcile fails it **skips the prune entirely** — a failed reconcile means the
desired state is unknown, so deleting anything would be unsafe.

`run_hook` handles the shell-operator calling convention: `--config`, logging,
reading the binding context, and the exit code.

## Adding a plugin

1. **Write the CRD** in `components/openstack-sync-operator/crds/`. Include a
   `status` subresource and a required `spec.cloudCredentialsRef` with
   `secretName` and `cloudName` — the framework relies on both. Put validation
   (`required`, `enum`, `minLength`, `default`) in the schema so the API server
   rejects bad CRs and the Python side does not have to re-check them.

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
   key into `MY_RESOURCE_<KEY>`. `HookConfig.from_env` reads exactly that set, so
   the chart and Python cannot drift apart.

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

**Only touch what you own.** Every plugin records ownership on the resources it
creates, and only ever updates or deletes resources carrying that marker. This is
what makes the operator safe to run against a cloud that also has hand-made
resources. Never adopt an existing resource by stamping the marker onto it —
that enrols somebody else's resource for eventual deletion.

**Report what you cannot fix.** `reconcile` returns a list of notes. Use it for
state that diverges from the spec but that OpenStack will not let the operator
correct — for example Neutron rejects `update_service_profile` with a 409 while
the profile is bound to any flavor. The resource is still `Synced`, but the notes
appear on the CR status and in the logs so an operator can act. Raise an
exception only for an actual failure.

## Tests

```sh
.venv/bin/python -m pytest tests/ -q
```

`tests/test_framework.py` exercises the driver with a stub plugin and no
OpenStack at all — read it first to understand the contract a plugin gets.
