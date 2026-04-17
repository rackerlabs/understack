# nautobot-target-proxy

Helm chart that deploys the `nautobot_target_proxy` FastAPI service.

## Behavior

- Runs the proxy as a Kubernetes `Deployment`.
- Exposes the app internally with a Kubernetes `Service`.
- Starts the container with `uvicorn app:app --host 0.0.0.0 --port 8000`.
- Injects `NAUTOBOT_URL` directly from values.
- Injects `UNDERSTACK_PARTITION` from the shared `cluster-data` ConfigMap.
- Injects `NAUTOBOT_TOKEN` from a referenced Kubernetes Secret.
- Uses TCP liveness and readiness probes on port `8000`.

## Image behavior

- Default image repository is `ghcr.io/rackerlabs/understack/nautobot-target-proxy`.
- Default tag comes from chart `appVersion` (currently `0.0.1`).
- You can override image repository/tag/pullPolicy in values.

## Required values

```yaml
nautobot:
  url: https://nautobot.example.com
  clusterDataConfigMapRef:
    name: cluster-data
    key: UNDERSTACK_PARTITION
  tokenSecretRef:
    name: nautobot-env
    key: NAUTOBOT_TOKEN
```

## Example values

```yaml
image:
  repository: ghcr.io/rackerlabs/understack/nautobot-target-proxy
  tag: "0.0.1"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 8000

nautobot:
  url: https://nautobot.example.com
  clusterDataConfigMapRef:
    name: cluster-data
    key: UNDERSTACK_PARTITION
  tokenSecretRef:
    name: nautobot-env
    key: NAUTOBOT_TOKEN
```

## Install

```bash
helm upgrade --install nautobot-target-proxy ./charts/nautobot-target-proxy -n nautobot
```
