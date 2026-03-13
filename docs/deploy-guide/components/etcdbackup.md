# etcdbackup

Scheduled etcd backup job configuration.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.etcdbackup`, `site.etcdbackup`
- ArgoCD Application template: `charts/argocd-understack/templates/application-etcdbackup.yaml`

## How ArgoCD Builds It

- ArgoCD renders only the sources declared directly in the Application template.
- The deploy repo contributes `values.yaml` for this component.
- The current template does not apply a deploy-repo overlay directory for this component.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  etcdbackup:
    enabled: true
site:
  etcdbackup:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the schedule, retention, storage destination, and any other Helm values for your backup policy.

## Notes

- The current ArgoCD template reads deploy-repo values for this component but does not apply a deploy overlay directory. Put configuration in `values.yaml`, not extra manifests.
