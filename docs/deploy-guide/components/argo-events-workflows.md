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

## Enrollment Workflow Configuration

Configure enrollment runbooks and post-enrollment templates through ConfigMaps
in the `argo-events` namespace:

| Workflow | ConfigMap |
| --- | --- |
| `enroll-server` | `enroll-server-config` |
| `enroll-fw` | `enroll-fw-config` |
| `enroll-netdev` | `enroll-netdev-config` |

Configuration values are JSON arrays:

| Key | Values | When it runs |
| --- | --- | --- |
| `post_inspection_runbooks` (`enroll-server` only) | Ironic runbook names or UUIDs | In list order after inspection and BIOS configuration, before RAID configuration, firmware updates, and making the node available. A failure stops enrollment. |
| `post_enroll_workflows` | `WorkflowTemplate` names | In parallel after enrollment. A failure fails the post-enrollment step. |

Create the ConfigMap in your deployment overlay. Replace the example names with
your runbooks and workflow templates; keep the parameter-source label.

```yaml title="configmap-enroll-server-config.yaml"
apiVersion: v1
kind: ConfigMap
metadata:
  name: enroll-server-config
  namespace: argo-events
  labels:
    workflows.argoproj.io/configmap-type: Parameter
data:
  post_inspection_runbooks: |
    [
      "first-runbook",
      "second-runbook"
    ]
  post_enroll_workflows: |
    [
      "notify-enrollment",
      "configure-monitoring"
    ]
```

Missing ConfigMaps or keys default to `[]`. Set a value to `[]` to disable it.
For a single server enrollment, override the runbooks with
`-p post_inspection_runbooks='["runbook"]'`, or pass `[]` to skip them.

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

Only the referenced `run` template is imported by `templateRef`. Put required
pod configuration on that template, or arrange for it on the parent enrollment
workflow; settings elsewhere in the referenced `WorkflowTemplate` spec are not
inherited. Hook pods use the service account of the parent workflow.
