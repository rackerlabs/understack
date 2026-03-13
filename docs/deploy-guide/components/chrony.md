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

## Notes

- The current ArgoCD template deploys the shared `components/chrony` base directly and does not read deploy-repo values or overlay manifests for this component.
- If you need site-specific time-server details, document them with the inventory or host provisioning content that consumes Chrony rather than in this Application.
