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

The `nautobot_config.py` file is managed in git at
`components/nautobot/nautobot_config.py` and injected into pods via the
Helm chart's `fileParameters` feature. ArgoCD reads the file, the Helm
chart creates a ConfigMap, and pods mount it at
`/opt/nautobot/nautobot_config.py`. The `NAUTOBOT_CONFIG` environment
variable tells Nautobot to load from that path.

The effective configuration is built from four layers: Nautobot defaults,
the component config, Helm chart env vars from the base values, and
deploy repo value overrides.

For the full details on how `fileParameters` works, why the baked-in
image config is not used, config layering, and the Helm list replacement
gotcha, see the
[Configuration Architecture](../../operator-guide/nautobot.md#configuration-architecture)
operator guide.

## Plugin Loading

For details on how plugins are loaded, configured via environment
variables, and how to add custom plugins, see the
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
| `mtls-ca-cert` | Certificate | CA public cert secret used by CNPG and Redis for client verification |
| `nautobot-cluster-server-tls` | Certificate | PostgreSQL server certificate |
| `nautobot-redis-server-tls` | Certificate | Redis server certificate |
| `nautobot-mtls-client` | Certificate | Client certificate for global Nautobot/Celery pods (needed because Redis `authClients: true` applies to all connections) |

All resources live in the `nautobot` namespace.

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

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide Nautobot runtime settings such as ingress, plugins, worker sizing, and feature flags.
- `nautobot-django` Secret: Provide a `NAUTOBOT_SECRET_KEY` value.
- `nautobot-redis` Secret: Provide a `NAUTOBOT_REDIS_PASSWORD` value.
- `nautobot-superuser` Secret: Provide `username`, `password`, `email`, and `apitoken` for the initial administrative account.

Optional additions:

- `nautobot-sso` Secret: Provide `client-id`, `client-secret`, and `issuer` when Nautobot authenticates through an external identity provider.
- `aws-s3-backup` Secret: Provide `access-key-id` and `secret-access-key` when scheduled backups are pushed to object storage.
- `dockerconfigjson-github-com` Secret: Provide `.dockerconfigjson` if Nautobot images or plugins come from a private registry.
- `nautobot-custom-env` Secret: Add any extra environment variables the deployment should inject into Nautobot, such as integration credentials or DSNs.
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
