---
kustomize_paths:
- workflows/argo-events
deploy_overrides:
  helm:
    mode: none
  kustomize:
    mode: second_source
---

# argo-events-workflows

Workflow templates that integrate Argo Events with the broader platform.

## Deployment Scope

- Cluster scope: site
- Values key: `site.argo_events_workflows`
- ArgoCD Application template: `charts/argocd-understack/templates/application-argo-events-workflows.yaml`

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## How to Enable

Enable this component under the scope that matches your deployment model:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  argo_events_workflows:
    enabled: true
```

## Deployment Repo Content

{{ secrets_disclaimer }}

Required or commonly required items:

- `nautobot-token` Secret: Provide `username`, `token`, and `hostname` so the workflow templates can authenticate to the source-of-truth API.
- `kustomization.yaml`: Include the Secrets and any additional workflow templates or parameter files that should be packaged with this overlay.

Optional additions:

- `Additional integration Secrets`: Add more Secrets beside the API token if individual workflows need their own credentials or endpoints.

## Enroll Server Configuration

Configure site-specific behavior for the `enroll-server` workflow by creating
an `enroll-server-config` ConfigMap in the `argo-events` namespace. The
`post_enroll_workflows` value is a JSON array of `WorkflowTemplate` names to run
after a server is enrolled:

```yaml title="enroll-server-config.yaml"
apiVersion: v1
kind: ConfigMap
metadata:
  name: enroll-server-config
  namespace: argo-events
  labels:
    workflows.argoproj.io/configmap-type: Parameter
data:
  post_enroll_workflows: |
    ["notify-enrollment", "configure-monitoring"]
```

The `workflows.argoproj.io/configmap-type: Parameter` label is required so the
Argo Workflows controller discovers the ConfigMap as a parameter source.

Each named `WorkflowTemplate` must be in the same namespace and expose a `run`
template that accepts the enrolled server's `node_uuid`:

{% raw %}

```yaml title="workflowtemplate-notify-enrollment.yaml"
apiVersion: argoproj.io/v1alpha1
kind: WorkflowTemplate
metadata:
  name: notify-enrollment
  namespace: argo-events
spec:
  templates:
    - name: run
      inputs:
        parameters:
          - name: node_uuid
      container:
        image: example.com/notify-enrollment:1.0.0
        args:
          - "{{inputs.parameters.node_uuid}}"
```

{% endraw %}

The hooks run in parallel as steps of the existing `enroll-server` workflow;
they do not create child `Workflow` resources. A failed hook fails the
post-enrollment step. If the ConfigMap or its key is absent, the hook list
defaults to empty and enrollment completes without running hooks.

Only the referenced `run` template is imported by `templateRef`. Put required
pod configuration on that template, or arrange for it on the `enroll-server`
workflow; settings elsewhere in the referenced `WorkflowTemplate` spec are not
inherited. Hook pods use the service account of the parent `enroll-server`
workflow.
