# ironic-hardware-exporter

A lightweight Go service that consumes Ironic's RabbitMQ notifications and
exposes them as Prometheus metrics.

## Problem It Solves

Ironic emits two useful families of events over RabbitMQ:

- **`hardware.<driver>.metrics`** for iDRAC/Redfish sensor readings
- **versioned node notifications** for power and provision state changes

Prometheus cannot consume either family directly. This service bridges that
gap by parsing both streams and presenting them on one `/metrics` endpoint.

## Architecture

```text
RabbitMQ  (ironic exchange)
    │
    ├── hardware.*.metrics
    │       └──► hardware consumer
    │               parse sensor event  (temperature, power, drive)
    │               call store.Update()
    │                       │
    │                       ▼
    │               ┌───────────────────────┐
    │               │    shared store       │──► GetAll snapshot ──► HTTP server :9608
    │               │  (NodeEntry per       │                              │
    │               │   node_uuid)          │                              ├──► /metrics  ──► Prometheus
    │               └───────────────────────┘                              │
    │                       ▲                                              └──► /health
    └── ironic_versioned_notifications.info                                     /ready  ──► Kubernetes
            └──► state consumer
                    parse state event  (power_state, provision_state, fault)
                    call store.UpdateNodeState()
```

## Two Consumers, One Cache

Both consumers share one `cache.Store`, protected by a read-write mutex.

- `Update()` writes sensor fields
- `UpdateNodeState()` writes state fields

Neither overwrites the other, so a node that has received sensor data but not
yet a state event, or vice versa, keeps whichever fields it already has.

The merge point is the `NodeEntry` type in `internal/cache/store.go`:

```text
NodeEntry
  NodeUUID, NodeName, LastSeen           ← from sensor events
  Sensors (Temperature/Power/Drive)      ← from sensor events
  ConductorHost, PowerState,
  ProvisionState, Maintenance,
  Fault                                  ← from state events
```

## Oslo Envelope

All Ironic RabbitMQ messages are double-wrapped in the Oslo messaging envelope:

```json
{
  "oslo.version": "2.0",
  "oslo.message": "<JSON-encoded inner message>"
}
```

Both parsers:

- `internal/parser/message.go`
- `internal/parser/node_state.go`

unwrap the outer envelope first, then decode the inner payload.

## Failure Behavior

If either consumer loses its RabbitMQ channel, the process should exit and let
Kubernetes restart it. The exporter should not keep serving stale partial data
with only one consumer alive.

Readiness reflects both consumers:

- `/health` = process is alive
- `/ready` = both RabbitMQ consumers are connected

## Metrics Exposed

Formatting lives in:

- `internal/server/formatter.go`

Key metric families:

| Metric | Type | Description |
|---|---|---|
| `ironic_node_last_seen_timestamp_seconds` | gauge | Unix timestamp of the last sensor event for this node |
| `ironic_node_temperature_celsius` | gauge | Temperature reading in Celsius per sensor |
| `ironic_node_power_output_watts` | gauge | Power supply output in watts |
| `ironic_node_drive_enabled` | gauge | 1 if drive is Enabled, 0 otherwise |
| `ironic_node_temperature_health` | gauge | Always 1; `health` label carries OK/Warning/Critical |
| `ironic_node_power_health` | gauge | Always 1; `health` label carries OK/Warning/Critical |
| `ironic_node_drive_health` | gauge | Always 1; `health` label carries OK/Warning/Critical |
| `ironic_node_power_state` | gauge | Always 1; `power_state` label carries current state |
| `ironic_node_provision_state` | gauge | Always 1; `provision_state` label carries current state |
| `ironic_node_maintenance` | gauge | 1 if node is in maintenance mode, 0 otherwise |
| `ironic_node_fault` | gauge | 1 if node has a fault, 0 if clean; `fault` label carries reason |

State metrics also carry:

- `node_uuid`
- `node_name`
- `conductor_host`

## Package Layout

```text
cmd/ironic-hardware-exporter/   entry point, wires consumers + cache + server
internal/
  config/     env-var loading, RabbitMQConfig and ServerConfig
  parser/     Oslo envelope parsing for both sensor and state events
  rabbitmq/   AMQP consumer (connect, declare queue, bind, consume loop)
  cache/      thread-safe NodeEntry store
  server/     HTTP server (/metrics, /health, /ready) and formatter
helm/         Helm chart for Kubernetes deployment
local/        local RabbitMQ TLS validation harness
```

## How To Build

### Binary

```bash
go build ./cmd/ironic-hardware-exporter/
```

### Run tests

```bash
GOCACHE=/tmp/gocache go test ./...
```

### Run race tests

```bash
go test -race ./...
```

### Container image

```bash
docker build -t ironic-hardware-exporter:dev .
```

### Release build

Release automation is defined in:

- `.goreleaser.yaml`
- `../../.github/workflows/build-ironic-hardware-exporter.yaml`

## How To Validate

### Local tests

```bash
GOCACHE=/tmp/gocache go test ./...
```

### Local RabbitMQ smoke test

The self-contained local environment lives under:

- `local/rabbitmq/`

Run a single TLS case:

```bash
GOCACHE=/tmp/gocache ./local/rabbitmq/smoke.sh tls
```

Run the full matrix:

```bash
GOCACHE=/tmp/gocache ./local/rabbitmq/smoke.sh all
```

This validates:

- plain AMQP
- TLS
- SNI override
- wrong CA failure
- wrong server-name failure
- end-to-end message flow to `/metrics`

### Manual checks

Once the exporter is running:

```bash
curl http://localhost:9608/health
curl http://localhost:9608/ready
curl -s http://localhost:9608/metrics | grep ironic_node
```

### Cluster validation

```bash
kubectl get pods -n <namespace>
kubectl logs -n <namespace> deploy/<release-name>
kubectl port-forward -n <namespace> svc/<release-name> 9608:9608
curl -s http://localhost:9608/metrics
```

If Prometheus is deployed in `monitoring`:

```bash
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090
```

Then query:

```promql
ironic_node_temperature_celsius
```

## How To Deploy

This service currently deploys as a standalone Helm chart. There is release
automation for the image and chart, but there is not yet an ArgoCD application
template for it in this repository.

### What gets built

Release automation is defined in:

- `.goreleaser.yaml`
- `../../.github/workflows/build-ironic-hardware-exporter.yaml`

That workflow:

- builds the container image
- packages the Helm chart from `helm/`
- publishes the chart to GHCR as an OCI chart

### What the chart deploys

The Helm chart creates:

- one `Deployment`
- one `Service`
- optionally one `ServiceMonitor`

Key deployment characteristics:

- singleton only
- no HPA
- no service account or RBAC requirement
- Prometheus scraping through `ServiceMonitor`

### Required Helm inputs

At minimum you should set:

- image tag
- RabbitMQ host
- RabbitMQ username
- RabbitMQ password Secret

Usually you will also set:

- `serviceMonitor.enabled=true`
- RabbitMQ TLS settings when the broker requires TLS

Important chart values live in:

- `helm/values.yaml`

The most important keys are:

- `image.repository`
- `image.tag`
- `rabbitmq.host`
- `rabbitmq.port`
- `rabbitmq.vhost`
- `rabbitmq.username`
- `rabbitmq.exchange`
- `rabbitmq.queue`
- `rabbitmq.routingKey`
- `rabbitmq.statesQueue`
- `rabbitmq.statesRoutingKey`
- `rabbitmq.existingSecret`
- `rabbitmq.passwordSecretKey`
- `rabbitmq.tls.enabled`
- `rabbitmq.tls.caSecretName`
- `rabbitmq.tls.caSecretKey`
- `rabbitmq.tls.serverName`
- `service.port`
- `serviceMonitor.enabled`

### Required Secrets

The chart expects a Kubernetes `Secret` containing the RabbitMQ password.

Example:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ironic-hardware-exporter-rabbitmq
type: Opaque
stringData:
  password: "<rabbitmq-password>"
```

If RabbitMQ TLS uses a private CA, create a CA Secret too:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ironic-hardware-exporter-rabbitmq-ca
type: Opaque
stringData:
  ca.crt: |
    -----BEGIN CERTIFICATE-----
    ...
    -----END CERTIFICATE-----
```

### Example values file

```yaml title="values-ironic-hardware-exporter.yaml"
image:
  repository: ghcr.io/rackerlabs/understack/ironic-hardware-exporter
  tag: "0.1.0"

rabbitmq:
  host: rabbitmq.openstack.svc.cluster.local
  vhost: ironic
  username: ironic
  exchange: ironic
  queue: ironic-hardware-exporter
  routingKey: notifications.info
  statesQueue: ironic-hardware-exporter-states
  statesRoutingKey: ironic_versioned_notifications.info
  existingSecret: ironic-hardware-exporter-rabbitmq
  passwordSecretKey: password
  tls:
    enabled: true
    caSecretName: ironic-hardware-exporter-rabbitmq-ca
    caSecretKey: ca.crt
    serverName: rabbitmq.openstack.svc.cluster.local

serviceMonitor:
  enabled: true
  interval: 30s
  scrapeTimeout: 10s
```

### Install from the local chart

```bash
helm upgrade --install ironic-hardware-exporter ./helm \
  --namespace openstack \
  --create-namespace \
  -f values-ironic-hardware-exporter.yaml
```

### Install from the published OCI chart

```bash
helm upgrade --install ironic-hardware-exporter \
  oci://ghcr.io/rackerlabs/charts/ironic-hardware-exporter \
  --version <chart-version> \
  --namespace openstack \
  --create-namespace \
  -f values-ironic-hardware-exporter.yaml
```

Adjust the GHCR owner if the chart is published under a different repository
owner.

### Post-install checks

Check the pod:

```bash
kubectl get pods -n openstack
kubectl logs -n openstack deploy/ironic-hardware-exporter
```

You want to see logs showing:

- sensor consumer connected
- state consumer connected
- HTTP server listening

Check the endpoints:

```bash
kubectl port-forward -n openstack svc/ironic-hardware-exporter 9608:9608
curl -s http://localhost:9608/health
curl -s http://localhost:9608/ready
curl -s http://localhost:9608/metrics
```

Expected behavior:

- `/health` returns `200`
- `/ready` returns `200`
- `/metrics` contains Ironic metrics

If `ServiceMonitor` is enabled, confirm Prometheus discovery:

```bash
kubectl get servicemonitor -n openstack
```

## Operational Notes

### Singleton only

This exporter keeps state in-process, so it must run as a singleton.

Do not scale it horizontally.

### Staleness model

The exporter retains the last known values in memory until a newer event
updates them.

There is no TTL-based expiry today.

### No RBAC requirement

The exporter does not call the Kubernetes API, so it does not require a
dedicated service account or RBAC permissions.
