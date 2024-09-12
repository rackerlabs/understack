# Overview

The WorkflowTemplates provided in this directory were created to establish commonly used Workflows to be consumed by other, likely larger, Workflows. For example,
the nautobot-api WorkflowTemplate is consumed by the get-device-nautobot WorkflowTemplate, to produce it's own output containing information on a Nautobot Device,
which can then be consumed by future WorkflowTemplates.

## Setup

The Nautobot Workflows require a ConfigMap.

```bash
kubectl -n argo create configmap nautobot '--from-literal=url=https://nautobot.local'
```

## Caveats

Currently Understack is not including any sort of secret store, outside of what is natively provided by Kubernetes. As such, these workflows make a couple of assumptions:

- Credentials will be mounted from a Kubernetes Secret.
- How those credential Secrets are created is up to you.

`workflowtemplates/get-bmc-creds.yaml` and the placeholder secret provided in `deps/` are strictly that, placeholder. They have been provided to allow the workflows to execute,
however they will likely fail until a proper get-bmc-creds Workflow is created.

## Example
```bash
argo -n argo-events submit --from workflowtemplate/get-device-nautobot --parameter device_id=1de4f169-9848-4d8e-921b-65338c1e00ca

Name:                get-device-nautobot-g5wlz
Namespace:           argo-events
ServiceAccount:      unset
Status:              Pending
Created:             Tue Apr 23 13:50:57 -0400 (now)
Progress:
Parameters:
  device_id:         1de4f169-9848-4d8e-921b-65338c1e00ca
```

```bash
argo -n argo-events get @latest

Name:                get-device-nautobot-g5wlz
Namespace:           argo-events
ServiceAccount:      workflow
Status:              Succeeded
Conditions:
 PodRunning          False
 Completed           True
Created:             Tue Apr 23 13:50:57 -0400 (38 seconds ago)
Started:             Tue Apr 23 13:50:57 -0400 (38 seconds ago)
Finished:            Tue Apr 23 13:51:27 -0400 (8 seconds ago)
Duration:            30 seconds
Progress:            1/1
Parameters:
  device_id:         1de4f169-9848-4d8e-921b-65338c1e00ca

STEP                          TEMPLATE           PODNAME  DURATION  MESSAGE
 ✔ get-device-nautobot-g5wlz  main
 └───✔ nautobot-query         nautobot-api/main
     └───✔ send-request       http
```
