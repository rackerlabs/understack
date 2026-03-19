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

- ArgoCD renders Helm chart `ingress-nginx`.
- The deploy repo contributes `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide controller service type, ingress class, load balancer, and default TLS behavior in `$CLUSTER_NAME/ingress-nginx/values.yaml`.

Optional additions:

- `Default certificate Secret`: If your values reference a default TLS certificate, create the Secret with `tls.crt` and `tls.key`.
