# cilium

Cilium networking resources that are supplied entirely from the deploy repo.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.cilium`, `site.cilium`
- ArgoCD Application template: `charts/argocd-understack/templates/application-cilium.yaml`

## How ArgoCD Builds It

- ArgoCD renders only the sources declared directly in the Application template.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  cilium:
    enabled: true
site:
  cilium:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `kustomization.yaml`: Include the network resources that define how Service IPs and announcements work in your environment.
- `Load balancer IP pool resources`: Create one or more IP pool manifests that reserve the address ranges exposed by your cluster.
- `L2 announcement policy resources`: Create the announcement policies that decide which Services are advertised and on which interfaces or nodes.

Optional additions:

- `Additional Cilium CRs`: Add more policies or pools for segmented networks, dedicated ingress ranges, or environment-specific failover behavior.
