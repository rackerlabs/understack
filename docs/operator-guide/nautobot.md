# Nautobot

## Related Guides

- [Nautobot Celery Queues](nautobot-celery-queues.md) -- configuring
  per-site Celery task queues and routing jobs to site-specific workers
- [mTLS Certificate Renewal](nautobot-mtls-certificate-renewal.md) --
  how mTLS client certificates for site workers are renewed and
  distributed across clusters

## PostgreSQL mTLS

All PostgreSQL connections -- both from global Nautobot pods and
site-level workers -- use mutual TLS with client certificate
authentication. The CNPG cluster enforces this with a single `pg_hba`
rule:

```text
hostssl all all 0.0.0.0/0 cert
```

This means every client must connect over TLS and present a valid
client certificate signed by the mTLS CA. The certificate CN is mapped
to the PostgreSQL user (`app`).

### CNPG Certificate Configuration

The CNPG Cluster resource has four certificate fields. Understanding
what each one does is critical for troubleshooting TLS errors:

| Field | Secret | What CNPG Does With It |
|---|---|---|
| `serverTLSSecret` | `nautobot-cluster-server-tls` | Mounted as the PostgreSQL server cert. Presented to clients during the TLS handshake. |
| `serverCASecret` | `mtls-ca-cert` | The `ca.crt` from this secret is sent to clients so they can verify the server cert (`sslrootcert` on the client side). |
| `clientCASecret` | `mtls-ca-cert` | The `ca.crt` from this secret populates PostgreSQL's `ssl_ca_file`. This is what PostgreSQL uses to verify client certificates during `pg_hba cert` auth. |
| `replicationTLSSecret` | `nautobot-cluster-replication` | Client cert (`CN=streaming_replica`) used for streaming replication between PostgreSQL instances. |

Key points:

- `clientCASecret` is the field that controls client cert verification.
  Without it, CNPG auto-generates its own internal CA and uses that for
  `ssl_ca_file`. External client certs signed by the mTLS CA will be
  rejected with `tlsv1 alert unknown ca`.
- `serverCASecret` does NOT populate `ssl_ca_file`. It only provides
  the CA cert that clients use to verify the server. This is a common
  source of confusion.
- `replicationTLSSecret` must be provided when setting `clientCASecret`.
  Without it, CNPG tries to generate its own replication cert and needs
  `ca.key` in the `clientCASecret` secret. Since `mtls-ca-cert` only
  has `ca.crt` (not the CA private key), CNPG fails with
  `missing ca.key secret data`.
- Both `clientCASecret` and `serverCASecret` can point to the same
  secret (`mtls-ca-cert`) when the same CA signs both server and client
  certificates.

### How nautobot_config.py Handles SSL

The `nautobot_config.py` SSL logic is gated on the `NAUTOBOT_DB_SSLMODE`
environment variable:

| Value | Behavior | Use Case |
|---|---|---|
| `verify-ca` | Sets `sslmode`, `sslcert`, `sslkey`, `sslrootcert` on the Django DB connection. Validates cert files exist at startup. | Global pods and site workers (production). |
| `verify-full` | Same as `verify-ca` but also verifies the server hostname matches the cert. | Stricter verification if needed. |
| `require` | Sets `sslmode=require` only. Encrypts the connection but does not present a client cert or verify the server CA. | Not suitable for `pg_hba cert` -- use `verify-ca` instead. |
| Unset or empty | No SSL options applied. Plain TCP connection. | Will be rejected by `hostssl ... cert` pg_hba rule. |

All pods (global and site) must set `NAUTOBOT_DB_SSLMODE=verify-ca` in
their `extraEnvVars` and have the mTLS client cert volume mounted at
`/etc/nautobot/mtls/`.

### Verifying the Certificate Chain

To confirm the CNPG cluster is using the correct CA for client cert
verification:

```bash
# Check what CA PostgreSQL is using for ssl_ca_file
kubectl exec -n nautobot nautobot-cluster-1 -c postgres -- \
  openssl x509 -noout -subject -issuer \
  -in /controller/certificates/client-ca.crt
# Expected: subject=CN=understack-mtls-ca

# Check the client cert CN and issuer
kubectl get secret nautobot-mtls-client -n nautobot \
  -o jsonpath='{.data.tls\.crt}' | base64 -d | \
  openssl x509 -noout -subject -issuer
# Expected: subject=CN=app, issuer=CN=understack-mtls-ca

# Verify the client cert against the CA
kubectl get secret mtls-ca-cert -n nautobot \
  -o jsonpath='{.data.ca\.crt}' | base64 -d > /tmp/ca.crt
kubectl get secret nautobot-mtls-client -n nautobot \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > /tmp/client.crt
openssl verify -CAfile /tmp/ca.crt /tmp/client.crt
# Expected: /tmp/client.crt: OK
```

### Common Errors

| Error | Cause | Fix |
|---|---|---|
| `tlsv1 alert unknown ca` | `clientCASecret` not set or points to wrong secret. CNPG uses its internal CA for `ssl_ca_file`. | Set `clientCASecret: mtls-ca-cert` and `replicationTLSSecret: nautobot-cluster-replication`. |
| `missing ca.key secret data` | `clientCASecret` set but `replicationTLSSecret` not provided. CNPG needs CA key to generate replication certs. | Add `replicationTLSSecret` with a cert-manager Certificate (`CN=streaming_replica`). |
| `connection requires a valid client certificate` | Client connected over TLS but did not present a cert. | Set `NAUTOBOT_DB_SSLMODE=verify-ca` on the pod. |
| `certificate authentication failed for user` | Client cert CN does not match the PostgreSQL user. | Ensure cert has `commonName: app`. |
| `x509: certificate signed by unknown authority` (CNPG status) | Old replication secret signed by CNPG's internal CA, not the mTLS CA. | Delete the old secret: `kubectl delete secret nautobot-cluster-replication -n nautobot`. cert-manager recreates it. |
| `no pg_hba.conf entry` | Client is not connecting over TLS, or the source IP / auth method does not match any rule. | Ensure `NAUTOBOT_DB_SSLMODE=verify-ca` is set. Check that the pg_hba rules cover the connection type. |

### Forcing CNPG to Reconcile

After changing certificate fields on the CNPG Cluster resource, the
operator may not immediately pick up the change. Force a reconcile:

```bash
kubectl annotate cluster nautobot-cluster -n nautobot \
  cnpg.io/reconcile=$(date +%s) --overwrite
```

Check the result:

```bash
kubectl get cluster nautobot-cluster -n nautobot \
  -o jsonpath='{.status.phase}{"\n"}{.status.phaseReason}{"\n"}'
```

If the phase is healthy, the change was applied. If it shows an error,
see the Common Errors table above.

### Handling Stale CNPG-Managed Secrets

When adding `replicationTLSSecret`, CNPG may have already created a
secret with the same name (e.g. `nautobot-cluster-replication`) using
its internal CA. cert-manager will not overwrite a secret it did not
create. You must delete the old secret first:

```bash
kubectl delete secret nautobot-cluster-replication -n nautobot
# cert-manager recreates it within seconds, signed by mtls-ca-issuer
```

Verify the new secret:

```bash
kubectl get secret nautobot-cluster-replication -n nautobot
# Should show DATA=3 (tls.crt, tls.key, ca.crt)

kubectl get secret nautobot-cluster-replication -n nautobot \
  -o jsonpath='{.data.tls\.crt}' | base64 -d | \
  openssl x509 -noout -subject -issuer
# Expected: subject=CN=streaming_replica, issuer=CN=understack-mtls-ca
```

Then force a CNPG reconcile (see above).

### Restarting CNPG Pods

If the CNPG pods have not picked up updated certificate secrets (e.g.
`client-ca.crt` still shows the old CA), use the `cnpg` kubectl plugin
to perform a rolling restart:

```bash
kubectl cnpg restart nautobot-cluster -n nautobot
```

This performs a rolling restart of all instances, handling replica/primary
ordering automatically and waiting for each pod to be ready before
proceeding.

If you only need pods to reload configuration (e.g. updated `pg_hba`
or PostgreSQL parameters) without a full restart:

```bash
kubectl cnpg reload nautobot-cluster -n nautobot
```

### pg_hba Behavior

pg_hba rules are evaluated top-to-bottom. PostgreSQL stops at the first
rule matching the connection type and source IP. If authentication fails
on that rule, the connection is rejected -- it does NOT fall through to
the next rule. This means two rules with the same
`hostssl all all 0.0.0.0/0` prefix makes the second unreachable. Use
CIDR scoping if you need different auth methods for different source
networks.

### Rollback to Password Auth

To revert global pods to password-based auth while keeping cert auth
for site workers:

1. Add back the `host` rule for local pods:

    ```yaml
    postgresql:
      pg_hba:
        - host all all 10.0.0.0/8 scram-sha-256
        - hostssl all all 0.0.0.0/0 cert
    ```

2. Remove `NAUTOBOT_DB_SSLMODE` from global pod `extraEnvVars` (keep
   it on site workers).

3. Optionally remove `clientCASecret` and `replicationTLSSecret` from
   the CNPG spec to let CNPG manage its own replication CA again.

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
