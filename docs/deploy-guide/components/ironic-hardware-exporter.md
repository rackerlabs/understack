---
charts:
- ironic-hardware-exporter
source_text: ArgoCD renders both the exporter Helm chart and the deploy-repo
  directory declared as a second source.
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: second_source
---

# ironic-hardware-exporter

RabbitMQ-driven Prometheus exporter for Ironic hardware and node-state metrics.

## Deployment Scope

- Cluster scope: site
- Values key: `site.ironic_hardware_exporter`
- ArgoCD Application template: `charts/argocd-understack/templates/application-ironic-hardware-exporter.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component in your site deployment values:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  ironic_hardware_exporter:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide site-specific Helm values such as RabbitMQ host, queue names, TLS settings, and optional `ServiceMonitor` tuning.
- `kustomization.yaml`: Include any Secrets or manifests that must be applied alongside the chart from the same deploy-repo directory.
- `RabbitMQ password Secret`: Create the Secret referenced by `rabbitmq.existingSecret`.

Optional additions:

- `RabbitMQ CA Secret`: Add a Secret containing `ca.crt` when `rabbitmq.tls.enabled=true` and the broker uses a private CA.
- `Additional overlay manifests`: Add SealedSecrets, ExternalSecrets, NetworkPolicies, or namespace-local overrides if this site needs extra deployment-specific resources.

## Notes

- This component uses a deploy-repo second source, so enabling it should normally create a site directory like `$CLUSTER_NAME/ironic-hardware-exporter/`.
- The chart itself lives in `go/ironic-hardware-exporter/helm` inside the UnderStack repo.
