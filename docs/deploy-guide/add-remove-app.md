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

To make changes you will need to add or modify files in `$DEPLOY_NAME/secrets/$APPLICATION/`
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
`apps/appsets/*.yaml` file that is appropriate for what you are

## Removing an application from UnderStack

[argocd]: <https://argo-cd.readthedocs.io/en/stable/>
[argocd-appset]: <https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/>
