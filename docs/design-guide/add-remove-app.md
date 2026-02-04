# Adding / Removing Components

UnderStack **Components** are deployed via [ArgoCD]
as [Applications][argocd-app], these are generated using [ArgoCD][argocd]'s
[ApplicationSet][argocd-appset] controller. This allows us to use common
patterns to deploy each of the components and allow specific environments
to modify or disable some components. See the [Configuring Components](../deploy-guide/component-config.md)
guide for more info on how to do so.

## Adding a Component to UnderStack

Adding a Component to UnderStack involves deciding on the correct ApplicationSet
(AppSet) to include it in, then going to that AppSet's directory in `apps/<appset>/`
and adding a YAML file which contains the Application configuration.

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
        - $deploy/{{.name}}/dex/values.yaml
      ignoreMissingValueFiles: true
  - ref: understack
    # path should only be here if you have manifests to load
    path: 'components/dex'
  - ref: deploy
    # only needed if manifests should be here
    path: '{{.name}}/dex'
```

{% endraw %}

### Configuring the namespace

If the namespace you'll be adding the component to is currently not in
use, you will have to add it to the appropriate AppProject for the
ApplicationSet in one of the following:

- `apps/appsets/project-understack-infra.yaml`
- `apps/appsets/project-understack-operators.yaml`
- `apps/appsets/project-understack.yaml`

## Removing an application from UnderStack

Removing a Component permanently from UnderStack is as easy as
deleting its YAML config from its AppSet in the `apps/<appset>/`
directory.

!!! note
    Remove the namespace from the AppProject if it is no longer
    in use.

[argocd]: <https://argo-cd.readthedocs.io/en/stable/>
[argocd-app]: <https://argo-cd.readthedocs.io/en/stable/user-guide/application-specification/>
[argocd-appset]: <https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/>
