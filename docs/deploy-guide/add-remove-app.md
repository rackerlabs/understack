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

To remove an application from being deployed, add or modify the `uc_skip_components`
annotation on the Kubernetes Secret which defines the cluster in the `argocd` namespace.
The `uc_skip_components` annotation is a string-ified JSON list of applications to
skip like:

```yaml
uc_skip_components: |
  ["metallb"]
```

## Adding an application to UnderStack

Adding an application to be part of UnderStack involves modifying the
`apps/appsets/*.yaml` file that is appropriate for what you are attempting to add.

The general form should be:

{% raw %}

```yaml
# list item per ArgoCD Application
# the component value will appear as the ArgoCD Application name
- component: dex
  # the below line can be added to install this into a different namespace than the component
  # componentNamespace: dex-system
  # this allows this component to not be installed
  skipComponent: '{{has "dex" ((default "[]" (index .metadata.annotations "uc_skip_components") | fromJson))}}'
  # defines all the sources used, the upstream chart or upstream source should come first
  # uc_repo_ in this context is the understack repo
  # uc_deploy_ in this context is the deploy specific repo
  sources:
    - repoURL: https://charts.dexidp.io
      chart: dex
      targetRevision: 0.16.0
      helm:
        releaseName: dex
        valueFiles:
        # this pulls defaults from the understack repo
          - $understack/components/dex/values.yaml
        # this pulls overrides from your deploy repo
          - $deploy/{{.name}}/helm-configs/dex.yaml
        # this makes it so the above don't have to exist
        ignoreMissingValueFiles: true
    - repoURL: '{{index .metadata.annotations "uc_repo_git_url"}}'
      targetRevision: '{{index .metadata.annotations "uc_repo_ref"}}'
      # path should only be here if you have manifests you want loaded
      path: 'components/dex'
      # ref is used above in the chart for the valueFiles
      ref: understack
    - repoURL: '{{index .metadata.annotations "uc_deploy_git_url"}}'
      targetRevision: '{{index .metadata.annotations "uc_deploy_ref"}}'
      # ref is used in the chart valueFiles
      ref: deploy
      # only needed if manifests should be here
      path: '{{.name}}/manifests/dex'
```

{% endraw %}

## Removing an application from UnderStack

[argocd]: <https://argo-cd.readthedocs.io/en/stable/>
[argocd-appset]: <https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/>
