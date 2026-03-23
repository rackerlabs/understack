---
charts:
- ingress-nginx
deploy_overrides:
  helm:
    mode: values
  kustomize:
    mode: none
---

# ingress-nginx

NGINX ingress controller deployment.

## Deployment Scope

- Cluster scope: global, site
- Values key: `global.ingress_nginx / site.ingress_nginx`
- ArgoCD Application template: `charts/argocd-understack/templates/application-ingress-nginx.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  ingress_nginx:
    enabled: true
```

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `values.yaml`: Provide controller service type, ingress class, load balancer, and default TLS behavior in `$CLUSTER_NAME/ingress-nginx/values.yaml`.

Optional additions:

- `Default certificate Secret`: If your values reference a default TLS certificate, create the Secret with `tls.crt` and `tls.key`.
