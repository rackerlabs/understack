# nautobot-site

Site-level Nautobot integration resources.

## Deployment Scope

- Cluster scope: site
- Values key: `site.nautobot_site`
- ArgoCD Application template: `charts/argocd-understack/templates/application-nautobot-site.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  nautobot_site:
    enabled: true
```

## How ArgoCD Builds It

- The deploy guide and chart README list `nautobot-site` as a site-scoped component.
- The current chart does not contain `charts/argocd-understack/templates/application-nautobot-site.yaml`, so there is not yet an ArgoCD source definition to describe here.
- Until that template exists, there is no deploy-repo values file or overlay directory consumed by ArgoCD for this page.

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- None today. Add the final Secret or manifest contract here when the `nautobot-site` Application template is implemented.

Optional additions:

- If you are carrying site-specific Nautobot resources out of tree, document them with the component that currently applies them rather than assuming a future `nautobot-site` Application.
