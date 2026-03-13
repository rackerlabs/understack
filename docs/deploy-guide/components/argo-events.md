# argo-events

Argo Events event sources, sensors, and helper resources.

## Deployment Scope

- Cluster scope: global or site
- Values keys: `global.argo_events`, `site.argo_events`
- ArgoCD Application template: `charts/argocd-understack/templates/application-argo-events.yaml`

## How ArgoCD Builds It

- ArgoCD renders Kustomize path `components/argo-events`.
- The current template does not read a deploy-repo `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
global:
  argo_events:
    enabled: true
site:
  argo_events:
    enabled: true
```

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `kustomization.yaml`: Include the workflow support resources and any site-specific ConfigMaps or Secrets that your sensors need.
- `Cluster metadata ConfigMap`: Provide the cluster facts that workflows consume, such as environment name, region identifier, service endpoints, DNS servers, and NTP servers.
- `core-creds` Secret: Provide `username` and `password` keys for any shared automation account used by event-driven jobs.
- `bmc-master` Secret: Provide a `key` value when hardware-management workflows need a master credential.
- `bmc-legacy-passwords` Secret: Provide a `passwords` key when workflows still need a flat password bundle.
- `undersync-token` Secret: Provide a `token` key if workflows call the undersync API.
- `deploy-repo-auth` Secret: Provide `ssh-privatekey` and `known_hosts` so workflows can clone or update deployment content.
- `dockerconfigjson-github-com` Secret: Provide `.dockerconfigjson` when workflow images are pulled from a private registry.

Optional additions:

- `Flavor metadata ConfigMap`: Add a ConfigMap that points workflows at a flavor catalog or other generated asset directory.
- `Namespace-specific metadata overlays`: Add per-namespace Kustomize overlays when the same cluster metadata must be copied into multiple namespaces.
- `Workflow RBAC`: Add Roles or RoleBindings if workflows need to create or update Secrets or other namespaced objects.
