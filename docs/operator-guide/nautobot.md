# Nautobot

## Related Guides

- [Nautobot Celery Queues](nautobot-celery-queues.md) -- configuring
  per-site Celery task queues and routing jobs to site-specific workers
- [mTLS Certificate Renewal](nautobot-mtls-certificate-renewal.md) --
  how mTLS client certificates for site workers are renewed and
  distributed across clusters

## Configuration Architecture

Nautobot requires a `nautobot_config.py` file that defines Django
settings, plugin loading, database options, and authentication
backends. In understack, this file lives at
`components/nautobot/nautobot_config.py` and is injected into pods
using the Helm chart's `fileParameters` feature.

### How fileParameters Works

Both the `nautobot` and `nautobot-worker` ArgoCD Applications use a
multi-source setup. The Helm chart source includes:

```yaml
helm:
  fileParameters:
    - name: nautobot.config
      path: $understack/components/nautobot/nautobot_config.py
```

ArgoCD reads the file content from the understack git repo and passes
it as the `nautobot.config` Helm value. The Nautobot Helm chart then
creates a ConfigMap from that content and mounts it into pods at
`/opt/nautobot/nautobot_config.py`. The `NAUTOBOT_CONFIG` environment
variable (set in the deploy repo values) tells Nautobot to load its
configuration from that path.

This approach means:

- The config file is version-controlled in git alongside the component
  it configures
- Changes to the config trigger ArgoCD syncs and pod restarts
  automatically (the Helm chart checksums the ConfigMap)
- The same config file is shared by both the global nautobot deployment
  and site-level workers, avoiding drift

### Why Not Use the Baked-In Config?

Container images may include their own `nautobot_config.py` at build
time (e.g. at `/opt/nautobot_config/nautobot_config.py`). While this
works for simple deployments, it has limitations:

- Config changes require rebuilding and redeploying the container image
- Different deployments (global vs site workers) may need different
  settings (e.g. mTLS, plugin sets) but share the same image
- Private deployment-specific settings (plugin credentials, SSO config)
  get baked into the image

The Helm `fileParameters` approach decouples the config from the image.
The image provides the runtime (Nautobot + installed plugins), while
the git-managed config and deploy-repo environment variables control
behavior. This separation allows:

- The same container image to be used across global and site deployments
  with different configurations
- mTLS, SSL, and other connection settings to be conditional on
  environment variables rather than hardcoded
- Private plugin configuration to be injected via environment variables
  in the deploy repo without modifying the public config file

### Config Layering

The effective configuration is built from multiple layers:

1. **Nautobot defaults** -- `from nautobot.core.settings import *`
   provides all default Django and Nautobot settings
2. **Component config** -- `components/nautobot/nautobot_config.py`
   overrides defaults with understack-specific settings (mTLS, plugin
   loading, SSO, partition identifier)
3. **Helm chart env vars** -- the base `components/nautobot/values.yaml`
   sets database, Redis, and other connection parameters as environment
   variables that the config reads via `os.getenv()`
4. **Deploy repo values** -- site-specific overrides (hostnames, image
   tags, extra plugins, credentials) that Helm merges on top of the
   base values

### Important: Helm List Replacement

Helm merges scalar and map values from multiple value files, but
**replaces lists entirely**. If the base `components/nautobot/values.yaml`
defines:

```yaml
nautobot:
  extraVolumes:
    - name: nautobot-sso
      secret:
        secretName: nautobot-sso
```

And the deploy repo values set:

```yaml
nautobot:
  extraVolumes:
    - name: mtls-certs
      secret:
        secretName: nautobot-mtls-client
```

The result is **only** `mtls-certs` -- the `nautobot-sso` volume is
gone. The deploy values must re-include any base volumes they need to
preserve.

## Plugin Loading

The shared `nautobot_config.py` (mounted via Helm `fileParameters`)
uses a generic plugin loading mechanism that works across different
container images and deployments:

1. Open-source plugins (`nautobot_plugin_nornir`, `nautobot_golden_config`)
   are loaded automatically if installed in the container image.
2. Additional plugins can be specified via the `NAUTOBOT_EXTRA_PLUGINS`
   environment variable (comma-separated module names). Each plugin is
   loaded only if it's actually installed in the container -- missing
   plugins are silently skipped.
3. Plugin configuration is provided via the `NAUTOBOT_EXTRA_PLUGINS_CONFIG`
   environment variable as a JSON object. This supports `${ENV_VAR}`
   syntax for referencing environment variables in string values, which
   is useful for injecting secrets at runtime without hardcoding them in
   the config.

This design allows the same `nautobot_config.py` to be used by both
the global Nautobot deployment (which may have additional private
plugins) and site workers (which may have a different plugin set),
without any deployment-specific code in the public repository.

Example deploy values for adding custom plugins:

```yaml
nautobot:
  extraEnvVars:
    - name: NAUTOBOT_EXTRA_PLUGINS
      value: 'my_custom_plugin,another_plugin'
    - name: NAUTOBOT_EXTRA_PLUGINS_CONFIG
      value: '{"my_custom_plugin":{"API_KEY":"${MY_API_KEY}"}}'
```

### Current Limitations

The `NAUTOBOT_EXTRA_PLUGINS_CONFIG` environment variable works but has
ergonomic drawbacks as the number of plugins grows:

- All plugin config is a single JSON string in the deploy values, which
  becomes hard to read and review in PRs
- JSON cannot express Python-native types like `None` or call functions
  like `is_truthy()` -- only plain JSON types (`null`, `false`, etc.)
- Adding or removing a plugin means editing a long inline JSON blob

### Future Improvement: Per-Plugin Config Files

A cleaner approach for deployments with many plugins is to store each
plugin's configuration as a separate JSON file in the deploy repo,
managed via a Kustomize `configMapGenerator`, and mounted into the pod
as a directory. The `nautobot_config.py` would then glob that directory
and load each file into `PLUGINS_CONFIG`.

Example structure in the deploy repo:

```text
<site>/nautobot/plugin-configs/
  nautobot_golden_config.json
  my_custom_plugin.json
  vni_custom_model.json
```

Each file contains the plugin's config as a JSON object:

```json title="my_custom_plugin.json"
{
  "API_KEY": "${MY_API_KEY}",
  "TIMEOUT": 30
}
```

A Kustomize `configMapGenerator` creates a ConfigMap from the directory:

```yaml title="kustomization.yaml"
configMapGenerator:
  - name: nautobot-plugin-configs
    files:
      - plugin-configs/nautobot_golden_config.json
      - plugin-configs/my_custom_plugin.json
    options:
      disableNameSuffixHash: true
```

The deploy values mount it as a volume:

```yaml
nautobot:
  extraVolumes:
    - name: plugin-configs
      configMap:
        name: nautobot-plugin-configs
  extraVolumeMounts:
    - name: plugin-configs
      mountPath: /etc/nautobot/plugin-configs
      readOnly: true
```

And the `nautobot_config.py` loads all files from the directory:

```python
import glob, json, os, re

def _interpolate_env(obj):
    if isinstance(obj, str):
        return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), obj)
    if isinstance(obj, dict):
        return {k: _interpolate_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interpolate_env(v) for v in obj]
    return obj

for _path in sorted(glob.glob("/etc/nautobot/plugin-configs/*.json")):
    _name = os.path.splitext(os.path.basename(_path))[0]
    with open(_path) as _f:
        PLUGINS_CONFIG[_name] = _interpolate_env(json.load(_f))
```

This gives each plugin its own readable file, makes PRs easy to review,
and keeps the `${ENV_VAR}` interpolation for secrets. It can be
implemented alongside the current env var approach without breaking
existing deployments.

## Nautobot Django shell

You can access the Nautobot Django shell by connecting to the pod and running the
`nautobot-server shell` command.

``` bash
# find one of the nautobot app pods
kubectl get pod -l app.kubernetes.io/component=nautobot-default
NAME                                READY   STATUS    RESTARTS   AGE
nautobot-default-598bddbc79-kbr72   1/1     Running   0          2d4h
nautobot-default-598bddbc79-lnjj6   1/1     Running   0          2d4h
```

``` bash
# use the nautobot-server shell
kubectl exec -it nautobot-default-598bddbc79-kbr72 -- nautobot-server shell
```

## Nautobot GraphQL Queries

### Query for all servers in a specific rack

This queries devices with the role `server` located in rack `rack-123`
and includes the iDRAC/iLO BMC IP address.

``` graphql
query {
  devices(role: "server", rack: "rack-123") {
    id
    name
    interfaces(name: ["iDRAC", "iLO"]) {
      ip_addresses {
        host
      }
    }
  }
}
```

Output example:

``` json title="rack-123-devices-output.json"
{
  "data": {
    "devices": [
      {
        "id": "4933fb3d-aa7c-4569-ae25-0af879a11291",
        "name": "server-1",
        "interfaces": [
          {
            "ip_addresses": [
              {
                "host": "10.0.0.1"
              }
            ]
          }
        ]
      },
      {
        "id": "f6be9302-96b0-47e9-ad63-6056a5e9a8f5",
        "name": "server-2",
        "interfaces": [
          {
            "ip_addresses": [
              {
                "host": "10.0.0.2"
              }
            ]
          }
        ]
      }
    ]
  }
}
```

Some jq to help parse the output:

``` bash
cat rack-123-devices-output.json | jq -r '.data.devices[] | "\(.id) \(.interfaces[0]["ip_addresses"][0]["host"])"'
```

Output:

``` text
4933fb3d-aa7c-4569-ae25-0af879a11291 10.0.0.1
f6be9302-96b0-47e9-ad63-6056a5e9a8f5 10.0.0.2
```
