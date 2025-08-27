# Configuring Components

The term **Component** in UnderStack is analogous to an [Application][argocd-app] in [ArgoCD][argocd].
It is typically tied to one Helm chart or Kustomize deployment. So OpenStack
Keystone is a **Component** in UnderStack, which lives in `components/keystone`
in the source tree. In some cases, like OpenStack services,
there are shared resources so UnderStack will have another **Component** called
openstack, which lives in `components/openstack` in the source tree, which
other OpenStack services depend on.

There are three different ways to alter the configuration of a **Component**
which depends on what you need to achieve.

1. Altering how and what ArgoCD deploys to the cluster
2. Altering the Helm values or Kustomize overlays
3. Altering state used by the containers that have been deployed

## Modifying the deployment

In your deployment repo, you will have `$DEPLOY_NAME/apps.yaml`
(see [Deploy Repo](./deploy-repo.md) for more details) which is
a list of objects, each object maps to one **Component** and must have
a field `component` with the string value matching an existing component.

### Disabling a component

To disable for example the `metallb` **Component** you would add to your
`apps.yaml` something like:

```yaml title="$DEPLOY_NAME/apps.yaml"
- component: metallb
  skip: true
```

The `skip` field is optional and assumed to be `false` otherwise but
if set to `true` will prevent ArgoCD from deploying it.

### Changing sources used by ArgoCD

We utilize [ArgoCD][argocd] [ApplicationSets][argocd-appset] to create
the [ArgoCD][argocd] [Applications][argocd-app].
In all cases we default the template to being a multi-source `Application`.
You can modify the sources that are used by default by editing your `$DEPLOY_NAME/apps.yaml`
To change this set your own `sources` list for the **Component** you wish to
modify. There are two special cased sources available which automatically
set the `repoUrl` and `targetRevision` fields which are the UnderStack repo
and your own deployment repo. These can be used by having a `ref` field with
the value `understack` or `deploy` respectively.

```yaml title="$DEPLOY_NAME/apps.yaml"
- component: argo
  sources:
    - ref: deploy
      path: deploy_name/manifests/argo-workflows
```

The above would replace the default behavior to only source from your
deployment repo for the `argo` **Component** from the specified path.

Another example would be:

```yaml title="$DEPLOY_NAME/apps.yaml"
- component: openstack
  sources:
    - ref: understack
      path: component/openstack
      helm:
        valueFiles:
          - $deploy/deploy_name/helm-configs/openstack.yaml
    - ref: deploy
```

This would utilize the Helm chart in the UnderStack repo while using the
values file from your deployment repo. This configuration is actually what
the default for this **Component** is.

You can see the defaults by looking in the `apps` directory in the UnderStack
repo under the `global`, `site`, and `openstack` directories.

## Modifying component Helm values or Kustomize

To create an environment specific modification to an **Component** you must
first determine if it's being deployed with Helm or Kustomize.

### Helm

Most of the applications can have their Helm values overridden by adding
or modifying `$DEPLOY_NAME/helm-configs/$COMPONENT.yaml` in your deployment
repo.

### Kustomize

To make changes you will need to add or modify files in `$DEPLOY_NAME/manifests/$COMPONENT/`
in your deployment repo.

## Modifying Environment State

TODO: more to come

[argocd]: <https://argo-cd.readthedocs.io/en/stable/>
[argocd-app]: <https://argo-cd.readthedocs.io/en/stable/user-guide/application-specification/>
[argocd-appset]: <https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/>
