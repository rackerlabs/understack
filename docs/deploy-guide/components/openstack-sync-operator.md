---
charts:
- components/openstack-sync-operator
deploy_overrides:
  helm:
    mode: values
---

# openstack-sync-operator

Deploys the OpenStack sync shell-operator in the OpenStack namespace.

This component owns the pieces that must version with hook code:

- the shell-operator Deployment
- the operator ServiceAccount
- the Role or ClusterRole used by enabled hooks
- the CRDs read by those hooks

It does not own plugin custom resources. Plugin CRs are plain YAML data applied
by the separate [`openstack-sync-plugins`](./openstack-sync-plugins.md)
Application.

## Deployment Scope

- Cluster scope: site
- Values key: `site.openstack_sync_operator`
- Helm chart: `components/openstack-sync-operator/`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openstack-sync-operator.yaml`
- Default namespace: `site.openstack.namespace`, normally `openstack`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## Related Plugin Application

The matching plugin data is deployed by
`charts/argocd-understack/templates/application-openstack-sync-plugins.yaml`.
That Application is Kustomize/raw YAML, not Helm. It reads:

```text
understack/components/openstack-sync-plugins/
deploy-repo/<site>/openstack-sync-plugins/
```

This split is intentional:

- CRDs live with the operator because they are the API contract consumed by hook
  code.
- RBAC lives with the operator because it grants permissions to the operator
  ServiceAccount.
- CRs live in the plugin Application because they are data, not runtime code.

Applying plugin CRs alone does not sync OpenStack. The matching hook must also
be enabled in the operator values, and the operator image must contain the hook
executable.

Important behavior:

- `site.openstack_sync_plugins.enabled` controls whether ArgoCD creates the
  plugin Application.
- The plugin Application applies every CR listed in
  `components/openstack-sync-plugins/kustomization.yaml` and
  `<deploy-repo>/<site>/openstack-sync-plugins/kustomization.yaml`.
- `plugins.<name>` does not control CR creation. It only controls the operator
  runtime for that hook: enablement env vars, hook RBAC, and the `verify-hooks`
  initContainer.

Because of that split, plugin CRs can exist while their hook is disabled. In
that state ArgoCD can be Synced, but the operator will not reconcile those CRs
into OpenStack.

## Enablement

Enable the operator Application in the site deploy values:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  openstack_sync_operator:
    enabled: true
```

Pin the operator image in the deployment repo:

```yaml title="$CLUSTER_NAME/openstack-sync-operator/values.yaml"
image:
  tag: <tag-or-digest>
```

The chart leaves `image.tag` unset by default, so Helm falls back to
`Chart.appVersion`. Site deployments should pin the image tag or digest they
intend to run in `<deploy-repo>/<site>/openstack-sync-operator/values.yaml`.

## Hook Enablement

Built-in hooks are declared in
`components/openstack-sync-operator/values.yaml`.
For each built-in CRD hook, the chart values use this shape:

```yaml
plugins:
  <name>: false

pluginData:
  <name>:
    hook:
      path: /hooks/<hook>.py
      crd: crds/<group>_<plural>.yaml
      envPrefix: <ENV_PREFIX>
```

Enable the hook from the deployment repo after the site is pinned to an
operator image built from this code:

```yaml title="$CLUSTER_NAME/openstack-sync-operator/values.yaml"
plugins:
  <name>: true
```

The image build in `containers/openstack-sync-operator/Dockerfile` copies the
enabled hook executables into `/hooks/`.

When `plugins.<name>: false`, that hook may still exist in the image but
publishes only a no-op startup binding. That keeps shell-operator startup valid
while preventing any watch, schedule, OpenStack sync, or hook-specific RBAC for
that resource.

When a hook is enabled, the chart:

- sets `<ENV_PREFIX>_ENABLED=true`
- derives CRD environment variables from the CRD file
- renders RBAC to `get`, `list`, and `watch` that CRD's resource
- renders status RBAC when the CRD has a `status` subresource
- adds the `verify-hooks` initContainer to fail fast if the hook executable is
  missing

`verify-hooks` is automatic. Plugin authors do not write this initContainer.
They declare the hook path in `pluginData.<name>.hook.path`, and the chart
generates one startup check for each enabled hook. The plugin author must still
copy the hook executable into the operator image at that path.

Rendered shape:

```yaml
initContainers:
- name: verify-hooks
  image: ghcr.io/rackerlabs/understack/openstack-sync-operator:...
  command:
  - /bin/sh
  - -ec
  - |
    missing=0
    if [ ! -x "/hooks/<hook>.py" ]; then
      echo "enabled hook <name> missing or not executable: /hooks/<hook>.py" >&2
      missing=1
    fi
    exit "${missing}"
```

Hook-specific OpenStack behavior belongs with the plugin's CR examples or schema
docs. This page documents only the operator deployment contract.

When no hook is enabled, the operator can still start. In that state the Role
has no custom-resource permissions and no OpenStack sync work is expected.

## Health Probes

The operator Deployment uses TCP liveness and readiness probes against
shell-operator's base HTTP port, `9115`.

This is chart behavior. Plugin authors do not need to implement a health
endpoint.

## RBAC

RBAC is rendered by
`components/openstack-sync-operator/templates/rbac.yaml.tpl`.
The chart starts with `rbac.rules` from values, then adds hook-specific rules
for each enabled hook.

Keep plugin RBAC in the operator chart. The permission is tied to the operator
ServiceAccount and to the hook code that uses it. Keeping RBAC with hook
enablement prevents this skew:

- CRs exist but the operator cannot read them.
- RBAC exists for a hook that is disabled or missing from the image.

The plugin Application should continue to apply only CR manifests.

## CRDs and Validation

The CRDs live under `components/openstack-sync-operator/crds/`.

Each plugin CRD defines:

- Scope: namespaced
- Status subresource: enabled
- Required `spec.cloudCredentialsRef.secretName`
- Required `spec.cloudCredentialsRef.cloudName`

The chart reads this CRD through
`components/openstack-sync-operator/templates/_crd.tpl` so
RBAC and hook environment variables are derived from the same schema Kubernetes
applies.

Plugin CR files can also reference editor schemas under:
`schema/openstack-sync/`

That schema focuses on plugin data under `spec`. Kubernetes validates the
full custom resource through the operator-owned CRD when ArgoCD applies it.

## Plugin CR Data

Shared plugin CRs live under:

`components/openstack-sync-plugins/`

Site-specific additions live in the deploy repo:

```text
<deploy-repo>/<site>/openstack-sync-plugins/
```

Use the plugin Application for these CRs. Do not pass CR lists through the
operator Helm values; changing CR data should not roll the operator Pod.

## Add a New Sync Hook

For each new sync hook, keep the same ownership split:

1. Add the CRD to `components/openstack-sync-operator/crds/`.
2. Add hook metadata under `pluginData.<name>.hook` in the operator chart values.
3. Add a `plugins.<name>` boolean defaulted to `false`.
4. Add the hook executable under `python/openstack-sync/openstack_sync/hooks/`
   and copy it into `/hooks/` from `containers/openstack-sync-operator/Dockerfile`.
5. Add shared CR YAML under `components/openstack-sync-plugins/`, or
   site-specific CR YAML under `<deploy-repo>/<site>/openstack-sync-plugins/`.
6. Enable the hook in `<deploy-repo>/<site>/openstack-sync-operator/values.yaml`
   after the image contains the hook.

That keeps API schema, hook runtime, RBAC, and CR data in the places that own
them.
