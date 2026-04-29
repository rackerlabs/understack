---
charts:
- nautobot
kustomize_paths:
- components/nautobot
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# nautobot

Global Nautobot deployment and its optional supporting resources.

## Deployment Scope

- Cluster scope: global
- Values key: `global.nautobot`
- ArgoCD Application template: `charts/argocd-understack/templates/application-nautobot.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  nautobot:
    enabled: true
```

## Configuration Architecture

The `nautobot_config.py` file is injected into pods via the Helm chart's
`fileParameters` feature. The default path is
`$understack/components/nautobot/nautobot_config.py`, but deployments can
override it with `global.nautobot.nautobot_config`. A deployment can
point this value at a shared deploy-repo config:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  nautobot:
    nautobot_config: '$deploy/apps/nautobot-config/nautobot_config.py'
```

ArgoCD reads the selected file, the Helm chart creates a ConfigMap, and
pods mount it at `/opt/nautobot/nautobot_config.py`. The
`NAUTOBOT_CONFIG` environment variable tells Nautobot to load from that
path.

The effective configuration is built from four layers: Nautobot defaults,
the selected `nautobot_config.py`, Helm chart env vars from the base
values, and deploy repo value overrides.

For the full details on how `fileParameters` works, why the baked-in
image config is not used, config layering, and the Helm list replacement
gotcha, see the
[Configuration Architecture](../../operator-guide/nautobot.md#configuration-architecture)
operator guide.

## Plugin Loading

Deployment-specific plugin configuration can live in the shared deploy
`nautobot_config.py`, with credentials supplied by `nautobot-custom-env`.
For details, see the
[Plugin Loading](../../operator-guide/nautobot.md#plugin-loading)
operator guide.

## mTLS Certificate Infrastructure

The global cluster hosts the mTLS CA hierarchy (managed by cert-manager)
used by both the global Nautobot deployment and site-level workers:

| Resource | Kind | Purpose |
|---|---|---|
| `mtls-selfsigned` | Issuer | Bootstraps the self-signed root |
| `mtls-ca` | Certificate | Root CA (ECDSA P-256, 10yr duration, 1yr renewBefore) |
| `mtls-ca-issuer` | Issuer | Signs all client and server certificates |
| `mtls-ca-cert` | Certificate | CA public cert secret used by CNPG (`clientCASecret` and `serverCASecret`) and Redis for client verification |
| `nautobot-cluster-server-tls` | Certificate | PostgreSQL server certificate |
| `nautobot-cluster-replication` | Certificate | Streaming replication client certificate (`CN=streaming_replica`). Required so CNPG does not need the CA private key in `clientCASecret`. |
| `nautobot-redis-server-tls` | Certificate | Redis server certificate |
| `nautobot-mtls-client` | Certificate | Client certificate for global Nautobot/Celery pods (`CN=app`). Used for both PostgreSQL `pg_hba cert` auth and Redis `authClients`. |
| `nautobot-mtls-client-<site>` | Certificate | Per-site worker client certificate (`CN=app`) issued on the global cluster and distributed to the site cluster through the secrets provider. |

All resources live in the `nautobot` namespace.

Client certificate naming:

- Global cluster `nautobot-mtls-client` is mounted directly by global
  Nautobot web and Celery pods.
- Global cluster `nautobot-mtls-client-<site>` is the source Secret for
  one site. Its cert/key are copied to the secrets provider.
- Site cluster `nautobot-mtls-client` is created by ExternalSecret from
  the provider data for that site and mounted by site workers.

For certificate renewal and distribution to site clusters, see the
[mTLS Certificate Renewal](../../operator-guide/nautobot-mtls-certificate-renewal.md)
operator guide.

## Redis mTLS

The global Redis instance has TLS enabled with `authClients: true`
(Bitnami Redis subchart), requiring client certificates from all
connections -- including local pods on the global cluster.

The `nautobot_config.py` Redis mTLS logic checks if the CA cert file
exists at the default path (`/etc/nautobot/mtls/ca.crt`). If present,
it configures `ssl_cert_reqs`, `ssl_ca_certs`, `ssl_certfile`, and
`ssl_keyfile` on the Redis connection pool, Celery broker, and Celery
result backend. Both global and site pods automatically pick up Redis
mTLS when the cert volume is mounted.

Because `authClients: true` applies to all connections (Redis has no
equivalent of `pg_hba` to distinguish local vs remote), the global
Nautobot deploy values must mount the `nautobot-mtls-client` cert into
both the web server and celery pods.

## PostgreSQL mTLS

The global CNPG cluster enforces client certificate authentication for
all connections via a single `pg_hba` rule:

```text
hostssl all all 0.0.0.0/0 cert
```

The CNPG Cluster resource configures four certificate fields:

| Field | Secret | Purpose |
|---|---|---|
| `serverTLSSecret` | `nautobot-cluster-server-tls` | Server cert presented to clients during TLS handshake |
| `serverCASecret` | `mtls-ca-cert` | CA cert sent to clients for server verification (`sslrootcert`) |
| `clientCASecret` | `mtls-ca-cert` | CA cert used by PostgreSQL's `ssl_ca_file` to verify client certs |
| `replicationTLSSecret` | `nautobot-cluster-replication` | Client cert for streaming replication (`CN=streaming_replica`) |

`clientCASecret` is the critical field for client cert verification.
Without it, CNPG auto-generates its own internal CA and uses that for
`ssl_ca_file`, causing `tlsv1 alert unknown ca` errors for external
client certs signed by the mTLS CA.

`replicationTLSSecret` must be provided alongside `clientCASecret` so
CNPG does not need the CA private key (`ca.key`) in the
`clientCASecret` secret. Without it, CNPG tries to generate its own
replication cert and fails with `missing ca.key secret data`.

Both global Nautobot pods and site workers set
`NAUTOBOT_DB_SSLMODE=verify-ca` to present their client certificates
(`CN=app`) during the TLS handshake. The `pg_hba cert` rule maps the
certificate CN to the PostgreSQL user.

Deployments may also set `NAUTOBOT_DB_SSLNEGOTIATION=direct` for both
global Nautobot pods and site workers. Only use `direct` when both
PostgreSQL and libpq are 17 or newer.

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide Nautobot runtime settings such as ingress, plugins, worker sizing, and feature flags.
- `nautobot-django` Secret: Provide a `NAUTOBOT_SECRET_KEY` value.
- `nautobot-redis` Secret: Provide a `NAUTOBOT_REDIS_PASSWORD` value.
- `nautobot-superuser` Secret: Provide `username`, `password`, `email`, and `apitoken` for the initial administrative account.
- `nautobot-custom-env` Secret: Required when using a deploy-specific config that reads additional integration credentials or runtime settings from environment variables.

Optional additions:

- `nautobot-sso` Secret: Provide `client-id`, `client-secret`, and `issuer` when Nautobot authenticates through an external identity provider.
- `aws-s3-backup` Secret: Provide `access-key-id` and `secret-access-key` when scheduled backups are pushed to object storage.
- `dockerconfigjson-github-com` Secret: Provide `.dockerconfigjson` if Nautobot images or plugins come from a private registry.
- `Database cluster and backup manifests`: Add a CloudNativePG cluster, backup schedule, or similar database resources if this deployment owns its own PostgreSQL cluster.
- `Catalog and bootstrap content`: Add app definitions, device types, location types, locations, rack groups, or racks if you want Nautobot preloaded with inventory metadata.

## Known Gotchas

- **Helm list values are replaced, not merged.** When the deploy repo
  values set `extraVolumes` or `extraVolumeMounts`, they completely
  replace the base values from `components/nautobot/values.yaml`. If
  the base values include volumes (e.g. SSO secret mounts), the deploy
  values must re-include them alongside any new volumes. Forgetting this
  will silently break features like SSO login.

- **Redis authClients affects all connections.** Redis
  `authClients: true` requires ALL clients (including global Nautobot
  pods) to present client certificates. The global Nautobot values must
  mount the mTLS client cert into both the web server and celery pods,
  not just site workers.
