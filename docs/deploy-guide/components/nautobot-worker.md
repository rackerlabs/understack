---
charts:
- nautobot
kustomize_paths:
- components/nautobot-worker
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# nautobot-worker

Site-level Nautobot Celery workers that connect to the global Nautobot
database and Redis. This component deploys only the Celery worker
portion of the Nautobot Helm chart on site clusters, allowing sites to
process background tasks locally without running the full Nautobot web
application. The web server, Redis, and PostgreSQL all remain on the
global cluster -- site workers connect back to those shared services
over the network.

## Deployment Scope

- Cluster scope: site
- Values key: `site.nautobot_worker`
- ArgoCD Application template: `charts/argocd-understack/templates/application-nautobot-worker.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component in your site deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  nautobot_worker:
    enabled: true
```

## Architecture

Site workers connect to the global cluster's PostgreSQL (CNPG) and Redis
through the Envoy Gateway. Both connections use mutual TLS (mTLS) with
TLS passthrough at the gateway, so the cryptographic handshake happens
directly between the worker pod and the database/Redis server.

```text
Site Cluster                          Global Cluster
+------------------+                  +---------------------------+
| Worker Pod       |  TLS+ClientCert  | Envoy Gateway             |
|  - celery        | ---------------> |  port 5432 (passthrough)  | --> CNPG PostgreSQL
|  - mtls certs    | ---------------> |  port 6379 (passthrough)  | --> Redis
+------------------+                  +---------------------------+
```

The worker pods mount a client certificate (issued by a dedicated
internal CA via cert-manager) and present it during the TLS handshake.
See [Certificate Infrastructure](#certificate-infrastructure) for
details on the CA hierarchy and how certificates are provisioned.
PostgreSQL and Redis on the global cluster verify the client certificate
against the same CA before accepting the connection.

### Why mTLS?

Site workers run on remote clusters and connect to the global database
and Redis over the network. Password-only authentication is insufficient
for cross-cluster connections -- if a credential leaks, any host with
network access could connect to the production database. mTLS ensures
that even with a leaked password, connections without a valid client
certificate are rejected. Traffic is encrypted end-to-end between the
worker pod and the server.

## Connection Security

### PostgreSQL (CNPG)

The global CNPG cluster is configured with:

- `spec.certificates.serverTLSSecret` and `spec.certificates.serverCASecret`
  for server-side TLS. PostgreSQL uses the CA in `serverCASecret` to
  verify client certificates presented during `pg_hba cert` authentication.
  `clientCASecret` is intentionally NOT set -- CNPG uses that field
  internally to sign replication client certificates, which requires the
  CA private key. CNPG manages its own replication client CA.
- `pg_hba` rules that require `hostssl ... cert` for remote connections
  and allow `host ... scram-sha-256` for local pods on the global cluster

Site workers connect with `sslmode=verify-ca`, presenting their client
certificate, key, and the CA root cert via Django's `DATABASES` OPTIONS.

The `nautobot_config.py` SSL logic is conditional on the
`NAUTOBOT_DB_SSLMODE` environment variable. When set to `verify-ca` or
`verify-full`, it reads the cert paths from environment variables (with
defaults pointing to `/etc/nautobot/mtls/`) and sets
`DATABASES["default"]["OPTIONS"]`. When the env var is unset or empty
(as on the global cluster), no SSL options are applied and pods connect
with password-only auth.

#### pg_hba Rule Order

The CNPG `pg_hba` rules are evaluated top-to-bottom:

1. `host all all 10.0.0.0/8 scram-sha-256` -- local pods on the global
   cluster connect with password only (no TLS required)
2. `hostssl all all 0.0.0.0/0 cert` -- remote connections with a valid
   client certificate are accepted (cert CN maps to DB user)
3. `hostssl all all 0.0.0.0/0 scram-sha-256` -- transitional rule:
   remote connections over TLS with password only (no client cert).
   Remove this rule once all sites have mTLS deployed.

### Redis

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
equivalent of `pg_hba` to distinguish local vs remote), a
`nautobot-mtls-client` Certificate resource is also deployed on the
global cluster so that local Nautobot web and Celery pods can present
a valid client cert.

### Envoy Gateway

Both PostgreSQL (port 5432) and Redis (port 6379) use `routes.tls`
entries with TLS passthrough mode. The gateway routes traffic based on
SNI hostname without terminating TLS, preserving end-to-end mTLS.

## Certificate Infrastructure

### Global Cluster

The global cluster hosts the mTLS CA hierarchy (managed by cert-manager):

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

### Site Clusters

Each site cluster needs:

1. The mTLS CA key pair distributed via your external secrets provider
   (secret name: `mtls-ca-key-pair`)
2. An `mtls-ca-issuer` Issuer referencing that secret
3. A `nautobot-mtls-client` Certificate resource that cert-manager uses
   to issue the client certificate (ECDSA P-256, 1yr duration, 30d
   auto-renewal)

The client certificate is mounted into worker pods at
`/etc/nautobot/mtls/` containing `tls.crt`, `tls.key`, and `ca.crt`.

## Adding a New Site

This section walks through configuring `nautobot-worker` for a new site
cluster. All files go in `<site-name>/nautobot-worker/` in the deploy
repo.

### Prerequisites

Before starting, ensure the global cluster already has:

- The mTLS CA hierarchy deployed (issuers, root CA, CA issuer)
- Server TLS certificates for PostgreSQL and Redis
- A global `nautobot-mtls-client` certificate (for Redis `authClients`)
- CNPG configured with `serverTLSSecret`, `serverCASecret`, and `pg_hba`
- Redis TLS enabled with `authClients: true`
- Envoy Gateway TLS passthrough routes on ports 5432 and 6379

You also need the mTLS CA key pair stored in your external secrets
provider so the site cluster can pull it.

### Step 1: Create the site directory

```text
<site-name>/nautobot-worker/
```

### Step 2: Create ExternalSecrets for credentials

Create ExternalSecret resources that pull credentials from your secrets
provider into the `nautobot` namespace. You need four:

| ExternalSecret | Target Secret | Purpose |
|---|---|---|
| `externalsecret-nautobot-django.yaml` | `nautobot-django` | Django `SECRET_KEY` -- must match the global instance |
| `externalsecret-nautobot-db.yaml` | `nautobot-db` | CNPG app user password (satisfies Helm chart requirement) |
| `externalsecret-nautobot-worker-redis.yaml` | `nautobot-redis` | Redis password |
| `externalsecret-dockerconfigjson-github-com.yaml` | `dockerconfigjson-github-com` | Container registry credentials |

Each ExternalSecret should reference your `ClusterSecretStore` and map
the credential into the key format the Nautobot Helm chart expects.

### Step 3: Create the mTLS CA key pair ExternalSecret

Create `externalsecret-mtls-ca-key-pair.yaml` to distribute the mTLS CA
certificate and private key to this site cluster. The resulting secret
must be a `kubernetes.io/tls` type with these keys:

| Key | Content |
|---|---|
| `tls.crt` | CA certificate (PEM) |
| `tls.key` | CA private key (PEM) |
| `ca.crt` | CA certificate (PEM, same as `tls.crt`) |

cert-manager's CA Issuer reads `tls.crt` and `tls.key` from this secret
to sign client certificates.

### Step 4: Create the cert-manager CA Issuer

Create `issuer-mtls-ca-issuer.yaml`:

```yaml
apiVersion: cert-manager.io/v1
kind: Issuer
metadata:
  name: mtls-ca-issuer
  namespace: nautobot
spec:
  ca:
    secretName: mtls-ca-key-pair
```

### Step 5: Create the client certificate

Create `certificate-nautobot-mtls.yaml`. The `commonName` must match the
PostgreSQL database user (typically `app`) because `pg_hba cert` maps
the certificate CN to the DB user.

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: nautobot-mtls-client
  namespace: nautobot
spec:
  secretName: nautobot-mtls-client
  duration: 8760h    # 1 year
  renewBefore: 720h  # 30 days
  commonName: app
  usages:
    - client auth
  privateKey:
    algorithm: ECDSA
    size: 256
  issuerRef:
    name: mtls-ca-issuer
    kind: Issuer
```

### Step 6: Create the kustomization

Create `kustomization.yaml` listing all resources:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - externalsecret-nautobot-django.yaml
  - externalsecret-nautobot-db.yaml
  - externalsecret-nautobot-worker-redis.yaml
  - externalsecret-dockerconfigjson-github-com.yaml
  - externalsecret-mtls-ca-key-pair.yaml
  - issuer-mtls-ca-issuer.yaml
  - certificate-nautobot-mtls.yaml
```

### Step 7: Create the values file

Create `values.yaml` with the site-specific overrides. Replace
`<env>` with your environment identifier and `<site-partition>` with
the site's partition name.

```yaml
nautobot:
  db:
    host: "nautobot-db.<env>.undercloud.rackspace.net"
  redis:
    host: "nautobot-redis.<env>.undercloud.rackspace.net"
    ssl: true
  image:
    registry: "ghcr.io"
    repository: "<org>/<nautobot-image>"
    tag: "latest"
    pullPolicy: "Always"
    pullSecrets:
      - dockerconfigjson-github-com

celery:
  extraEnvVars:
    - name: NAUTOBOT_CONFIG
      value: /opt/nautobot/nautobot_config.py
    - name: UC_PARTITION
      value: <site-partition>
    - name: NAUTOBOT_DB_SSLMODE
      value: verify-ca
    - name: NAUTOBOT_REDIS_SSL_CERT_REQS
      value: required
    - name: NAUTOBOT_REDIS_SSL_CA_CERTS
      value: /etc/nautobot/mtls/ca.crt
    - name: NAUTOBOT_REDIS_SSL_CERTFILE
      value: /etc/nautobot/mtls/tls.crt
    - name: NAUTOBOT_REDIS_SSL_KEYFILE
      value: /etc/nautobot/mtls/tls.key
    - name: SSL_CERT_FILE
      value: /etc/nautobot/mtls/ca.crt
    - name: REQUESTS_CA_BUNDLE
      value: /etc/nautobot/mtls/ca.crt
  extraVolumes:
    - name: mtls-certs
      secret:
        secretName: nautobot-mtls-client
        defaultMode: 256
  extraVolumeMounts:
    - name: mtls-certs
      mountPath: /etc/nautobot/mtls
      readOnly: true
```

### Step 8: Enable in deploy.yaml

Add `nautobot_worker` to the site's `deploy.yaml`:

```yaml
site:
  nautobot_worker:
    enabled: true
```

### Step 9: Verify

After ArgoCD syncs, verify the worker is running and connected:

```bash
# Check the certificate was issued
kubectl get certificate nautobot-mtls-client -n nautobot

# Check the worker pod is running
kubectl get pods -n nautobot -l app.kubernetes.io/component=nautobot-celery

# Check worker logs for successful DB/Redis connections
kubectl logs -n nautobot -l app.kubernetes.io/component=nautobot-celery --tail=50
```

### Final directory structure

```text
<site-name>/nautobot-worker/
  certificate-nautobot-mtls.yaml
  externalsecret-dockerconfigjson-github-com.yaml
  externalsecret-mtls-ca-key-pair.yaml
  externalsecret-nautobot-db.yaml
  externalsecret-nautobot-django.yaml
  externalsecret-nautobot-worker-redis.yaml
  issuer-mtls-ca-issuer.yaml
  kustomization.yaml
  values.yaml
```

## Environment Variable Reference

| Variable | Where Set | Purpose |
|---|---|---|
| `NAUTOBOT_DB_SSLMODE` | Site worker values | Controls PostgreSQL SSL mode. Set to `verify-ca` for mTLS. Unset on global cluster. |
| `NAUTOBOT_DB_SSLCERT` | Optional override | Path to client cert for PG (default: `/etc/nautobot/mtls/tls.crt`) |
| `NAUTOBOT_DB_SSLKEY` | Optional override | Path to client key for PG (default: `/etc/nautobot/mtls/tls.key`) |
| `NAUTOBOT_DB_SSLROOTCERT` | Optional override | Path to CA cert for PG (default: `/etc/nautobot/mtls/ca.crt`) |
| `NAUTOBOT_REDIS_SSL_CERT_REQS` | Site worker values | Set to `required` to enforce Redis server cert verification |
| `NAUTOBOT_REDIS_SSL_CA_CERTS` | Site worker values | Path to CA cert for Redis |
| `NAUTOBOT_REDIS_SSL_CERTFILE` | Site worker values | Path to client cert for Redis |
| `NAUTOBOT_REDIS_SSL_KEYFILE` | Site worker values | Path to client key for Redis |
| `SSL_CERT_FILE` | Site worker values | System-wide CA bundle override for outbound HTTPS |
| `REQUESTS_CA_BUNDLE` | Site worker values | Python requests library CA bundle override |
| `NAUTOBOT_CONFIG` | Both global and site | Path to `nautobot_config.py` |
| `UC_PARTITION` | Site worker values | Site partition identifier for Celery task routing |

## Design Decisions

- The cert-manager CA hierarchy (self-signed bootstrap -> root CA ->
  CA issuer) handles issuance and renewal on both global and site
  clusters without manual intervention.

- CNPG's native TLS support (`serverTLSSecret`, `serverCASecret`)
  integrates directly with cert-manager secrets. No sidecar proxies or
  custom TLS termination needed. PostgreSQL verifies external client
  certificates using the CA chain from `serverCASecret` when processing
  `pg_hba cert` rules.

- The `routes.tls` type in the Envoy Gateway template uses a
  `gatewayPort` field to support non-443 ports for TLS passthrough.
  PostgreSQL (5432) and Redis (6379) both use this route type.

- The `pg_hba cert` method with CN-to-user mapping means the client
  certificate CN (e.g. `app`) maps directly to the PostgreSQL user, so
  no additional user mapping configuration is needed.

- The CA key pair is distributed to site clusters via the external
  secrets provider, following the existing credential distribution
  pattern.

- The `nautobot_config.py` SSL logic is conditional on
  `NAUTOBOT_DB_SSLMODE`, so the same config file works for both global
  pods (no mTLS) and site workers (mTLS enabled).

- The Redis mTLS logic in `nautobot_config.py` auto-detects the CA cert
  file at the default mount path. If the cert volume is mounted, Redis
  mTLS is configured automatically.

## Known Gotchas

- **clientCASecret is NOT for external client verification.** CNPG's
  `clientCASecret` field is used internally to sign replication client
  certificates between PostgreSQL instances. It expects a secret with
  both `ca.crt` and `ca.key`. Only `serverTLSSecret` and
  `serverCASecret` should be set. PostgreSQL verifies external client
  certificates using the CA chain from `serverCASecret` when processing
  `pg_hba cert` rules.

- **SSL config must be conditional.** Setting `sslmode` unconditionally
  in `nautobot_config.py` would break global cluster pods, which connect
  to CNPG via local password-only auth. The SSL config is gated on the
  `NAUTOBOT_DB_SSLMODE` env var -- global pods don't set it, so they
  are unaffected.

- **mtls-ca-cert secret contains a private key.** cert-manager
  Certificate resources always produce `tls.crt`, `tls.key`, and
  `ca.crt`. CNPG only reads `ca.crt` from the referenced secret, so
  the extra fields are harmless but not ideal. A future improvement
  could use cert-manager `trust-manager` Bundle to distribute only the
  CA cert.

- **ExternalSecret regex splitting is fragile.** If your external
  secrets provider stores the CA cert and key concatenated in a single
  field, the ExternalSecret template uses regex to split them. Changes
  to the credential format can break the regex.

- **Redis authClients affects all connections.** Redis
  `authClients: true` requires ALL clients (including global Nautobot
  pods) to present client certificates. The global Nautobot values must
  mount the mTLS client cert into both the web server and celery pods,
  not just site workers.

- **pg_hba rule ordering matters.** The transitional `pg_hba` rules
  (`hostssl ... cert` and `hostssl ... scram-sha-256` for remote) are
  ordered so that cert-based auth is tried first. Sites without client
  certs fall through to password-only over TLS. Once all sites have
  mTLS deployed, the `scram-sha-256` remote rule should be removed.

- **defaultMode 256 vs 0400.** The `defaultMode: 256` (octal 0400) on
  the cert secret volume mount is correct but easy to get wrong. YAML
  interprets `0400` as octal (decimal 256) -- writing `256` explicitly
  avoids ambiguity.

- **Client cert CN must match the DB user.** When using `pg_hba cert`
  auth, PostgreSQL maps the client certificate CN to the database user.
  The site worker client cert must use `commonName: app` to match the
  CNPG app user. If the CN doesn't match, the connection is rejected
  even with a valid cert.

## Troubleshooting

### Worker pod fails to start with FileNotFoundError

The `nautobot_config.py` validates that cert files exist when
`NAUTOBOT_DB_SSLMODE` is `verify-ca` or `verify-full`. If the
`nautobot-mtls-client` secret doesn't exist or the volume mount is
misconfigured, the pod will crash with:

```text
FileNotFoundError: SSL certificate file required by NAUTOBOT_DB_SSLCERT not found: /etc/nautobot/mtls/tls.crt
```

Check that:

1. The `certificate-nautobot-mtls.yaml` Certificate resource exists and
   is in `Ready` state: `kubectl get certificate -n nautobot`
2. The `nautobot-mtls-client` secret was created by cert-manager:
   `kubectl get secret nautobot-mtls-client -n nautobot`
3. The `mtls-ca-key-pair` secret exists (needed by the Issuer):
   `kubectl get secret mtls-ca-key-pair -n nautobot`
4. The `mtls-ca-issuer` Issuer is in `Ready` state:
   `kubectl get issuer -n nautobot`

### PostgreSQL rejects connection with "certificate verify failed"

The client cert is not signed by the CA that CNPG trusts. Verify the
CA chain:

```bash
# On the site cluster, check the client cert's issuer
kubectl get secret nautobot-mtls-client -n nautobot \
  -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -issuer

# On the global cluster, check the CA cert that CNPG uses
kubectl get secret mtls-ca-cert -n nautobot \
  -o jsonpath='{.data.ca\.crt}' | base64 -d | openssl x509 -noout -subject
```

The issuer of the client cert should match the subject of the CA cert.

### PostgreSQL rejects with "no pg_hba.conf entry"

The connection doesn't match any `pg_hba` rule. Common causes:

- The client is connecting without TLS but the only matching rule
  requires `hostssl`
- The client cert CN doesn't match the DB user (for `cert` auth)
- The source IP doesn't match any rule's CIDR

### Redis connection refused with TLS error

If Redis has `authClients: true` and the connecting pod doesn't present
a client cert, the TLS handshake fails. Ensure the pod has the mTLS
cert volume mounted and the Redis SSL env vars are set.

### Envoy Gateway not routing traffic

If the gateway listener doesn't appear or traffic isn't reaching the
backend:

```bash
# Check gateway status
kubectl get gateway -n envoy-gateway -o yaml

# Check TLSRoute status
kubectl get tlsroute -n nautobot -o yaml
```

Verify the `fqdn` in the TLS route matches the SNI hostname the client
is connecting to. For PostgreSQL, the `nautobot.db.host` in the worker
values must match the `fqdn` in the envoy-configs route.
