# Nautobot mTLS Certificate Renewal

This guide covers how mTLS client certificates used by site-level
Nautobot workers are renewed and distributed across clusters.

For background on the mTLS architecture and certificate infrastructure,
see the [nautobot-worker deploy guide](../deploy-guide/components/nautobot-worker.md).

## How Certificates Are Issued

Client certificates are issued by cert-manager on the global cluster
using the `mtls-ca-issuer` (backed by a self-signed root CA). Each site
gets its own Certificate resource:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: nautobot-mtls-client-<site>
  namespace: nautobot
spec:
  secretName: nautobot-mtls-client-<site>
  duration: 26280h   # 3 years
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

cert-manager automatically renews the certificate 90 days before
expiry, updating the Kubernetes secret on the global cluster.

## The Distribution Problem

cert-manager handles renewal on the global cluster automatically. The
challenge is getting the renewed certificate to the site cluster. The
site cluster pulls the cert from an external secrets provider via an
ExternalSecret resource. When cert-manager renews the cert, the updated
material must be pushed to the secrets provider so the site
ExternalSecret picks it up on its next refresh cycle.

By default, this is a manual process: an operator extracts the renewed
cert from the global cluster and uploads it to the secrets provider.

## Automation Approaches

### PushSecret (External Secrets Operator)

Use a [PushSecret](https://external-secrets.io/latest/guides/pushsecrets/)
resource on the global cluster to automatically push the renewed cert
to your secrets provider whenever the Kubernetes secret changes. This
is event-driven and requires no CronJob.

This is the recommended approach if your secrets provider is supported
by the External Secrets Operator.

### CronJob on the Global Cluster

A Kubernetes CronJob that runs periodically, reads the cert secret, and
pushes it to your secrets provider via its API. Simple to implement but
introduces a delay between renewal and distribution (up to the CronJob
interval).

### Cross-Cluster Secret Replication

Use a tool like
[Kubernetes Replicator](https://github.com/mittwald/kubernetes-replicator)
to copy the cert secret directly from the global cluster to site
clusters, bypassing the secrets provider entirely. Requires network
connectivity between clusters and appropriate RBAC.

### CertificateRequest from Site Clusters

The site cluster creates a cert-manager
[CertificateRequest](https://cert-manager.io/docs/usage/certificaterequest/),
an operator on the global cluster approves and signs it, and the signed
cert is returned. This is similar to how kubelet certificate management
works in Kubernetes. Most complex to set up but fully automated with no
intermediate secrets provider.

## Monitoring Certificate Expiry

Check certificate status on the global cluster:

```bash
# List all mTLS client certificates and their expiry
kubectl get certificate -n nautobot -o custom-columns=\
NAME:.metadata.name,\
READY:.status.conditions[0].status,\
EXPIRY:.status.notAfter,\
RENEWAL:.status.renewalTime

# Check a specific site's certificate
kubectl describe certificate nautobot-mtls-client-<site> -n nautobot
```

On the site cluster, verify the ExternalSecret is syncing:

```bash
kubectl get externalsecret nautobot-mtls-client -n nautobot
```

If the ExternalSecret shows `SecretSyncedError`, the credential in
your secrets provider may be stale or missing.

## What Happens When a Certificate Expires

If a site worker's client certificate expires before it is renewed and
distributed:

- PostgreSQL connections fail with `SSL error: certificate has expired`
- Redis connections fail with `[SSL: CERTIFICATE_VERIFY_FAILED]`
- The worker pod stays running but all tasks fail
- The health check reports Redis as unavailable

To recover, manually extract the renewed cert from the global cluster
and upload it to your secrets provider. The site ExternalSecret will
pick it up on the next refresh cycle, and the worker pods will
automatically get the new cert on their next restart (or when the
secret volume is refreshed by kubelet).
