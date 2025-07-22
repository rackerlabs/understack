# Adding / Removing Applications

The applications that are deployed using [ArgoCD][argocd]'s
[ApplicationSet][argocd-appset] controller. This allows us to use common
patterns to deploy each of the applications and allow specific environments
to modify or disable some applications.

## Modifying an application

To create an environment specific modification to an application you must
first determine if it's being deployed with Helm or Kustomize.

### Helm

Most of the applications can have their Helm values overridden by adding
or modifying `$DEPLOY_NAME/helm-configs/$APPLICATION.yaml` in your deployment
repo.

### Kustomize

To make changes you will need to add or modify files in `$DEPLOY_NAME/manifests/$APPLICATION/`
in your deployment repo.

## Removing an application for a specific deploy

To remove an application from being deployed, create an `apps.yaml` file in your deployment
repo at `$DEPLOY_NAME/apps.yaml`). The `apps.yaml` file
contains a list of objects, where each object has a `component` field that is the name
of the component (app) and an optional `skip` field that can be set to `true`:

```yaml
- component: metallb
  skip: true
- component: dex
  skip: false  # optional, defaults to false
```

## Adding an application to UnderStack

Adding an application to UnderStack involves deciding on the correct ApplicationSet
(AppSet) to include it in, then going to that AppSet's directory in `apps/<appset>/`
and adding a YAML file which contains the application configuration.

The YAML file should contain:

- A `component` field that matches the application name
- All sources necessary to load the application
- A `ref` field set to either `understack` or `deploy` instead of explicitly
  specifying `repoURL` and `targetRevision` for the UnderStack repo and your deploy repo

Example application configuration:

{% raw %}

```yaml
component: dex
# optional: install into a different namespace than the component name
# componentNamespace: dex-system
sources:
  - repoURL: https://charts.dexidp.io
    chart: dex
    targetRevision: 0.16.0
    helm:
      releaseName: dex
      valueFiles:
        # pulls defaults from the understack repo
        - $understack/components/dex/values.yaml
        # pulls overrides from your deploy repo
        - $deploy/{{.name}}/helm-configs/dex.yaml
      ignoreMissingValueFiles: true
  - ref: understack
    # path should only be here if you have manifests to load
    path: 'components/dex'
  - ref: deploy
    # only needed if manifests should be here
    path: '{{.name}}/manifests/dex'
```

{% endraw %}

## Removing an application from UnderStack

Removing an application permanently from UnderStack is as easy as
deleting its YAML config from its AppSet in the `apps/<appset>/`
directory.

[argocd]: <https://argo-cd.readthedocs.io/en/stable/>
[argocd-appset]: <https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/>
