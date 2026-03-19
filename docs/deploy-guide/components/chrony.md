# chrony

Chrony integration for OpenStack nodes.

## Deployment Scope

- Cluster scope: site
- Values key: `site.chrony`
- ArgoCD Application template: `charts/argocd-understack/templates/application-chrony.yaml`

## How ArgoCD Builds It

- ArgoCD renders Kustomize path `components/chrony`.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  chrony:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- None for this Application today. It deploys the shared `components/chrony` base directly and does not consume deploy-repo values or overlay manifests for this component.

Optional additions:

- Document site-specific time-server configuration with the inventory or host provisioning content that consumes Chrony rather than on this Application page.
