# Argo Workflows

[Argo Workflows][argo-workflows] was chosen as our workflow / orchestration service. It runs natively inside a
Kubernetes environment and easily integrates with [Argo Events][argo-events]. Understack will be deployed with the
set of WorkflowTemplates below.

## WorkflowTemplates

| WorkflowTemplate      | Description                                               | Input                   | Output     |   |
|---------------------- |-----------------------------------------------------------|-------------------------|------------|---|
| get-device-nautobot   | Return Device Information from Nautobot                   | hostname                | device     |   |
| get-obm-creds         | Get the credentials for the target Device                 | hostname                | secret     | * |
| get-obm-ip            | Get OBM IP address for target Device                      | hostname                | ip         |   |
| nautobot-api          | HTTP Template Workflow to query the Nautobot API          | method,nautobot_url,uri | result     |   |
| obm-firmware-update   | Update OBM firmware on target Device                      | hostname                |            |   |
| obm-sync-creds        | Sync's a devices OBM password with what we have on record | hostname                |            |   |

\* WorkflowTemplate which requires a manual / custom implementation.

As Understack develops, there may be underlying / dependant services which are not included, and require some of the
included WorkflowTemplates to be manually implemented to work in your environment. For example, the get-obm-creds
WorkflowTemplate will need to be written to communicate with whatever service you're using to store your device
credentials.

## Setup

The included Workflows include references to configuration ConfigMaps and Secrets.

### Nautbot

The Secret will be defined by the External Secret.

```bash
kubectl -n argo create configmap nautobot '--from-literal=url=https://nautobot.local'
```

## Security

Authorization is handled by Kubernetes' RBAC services. Workflows are run with the context of a given Kubernetes Service
Account. We've provided the `workflow` Service Account, which has been granted access to the necessary Kubernetes
resources, to run the provided WorkflowTemplates.

### argo-python

To facilitate the ability to pass data securely between Workflows the [argo-python][argo-python] Class was written.
This Python Class writes Kubernetes Secrets directly to the Kubernetes API from the Workflow's Pod, allowing these
Secrets to be securely mounted into a subsequent Workflow's environment.

By default these Secrets are created with an ownerReference set to the Pod which created them, which allows them to be
garbage collected when that Pod is terminated. This ownerReference requires a Kubernetes Pod uid which can be obtained
from the Kubernetes API, requiring Pod `get` permissions to be granted to the Workflow's Service Account. Alternatively
the Pod's uid can be passed via the `KUBERNETES_POD_UID` environment variable. To allow the owner Pod to be removed at
completion of the Workflow `.spec.podGC.strategy` can be set to `OnWorkflowCompletion`.

An example WorkflowTemplate demonstrating argo-python usage can be found
[here](https://github.com/rackerlabs/understack/blob/main/workflows/argo-events/workflowtemplates/get-obm-creds.yaml).

### Argo CLI

Argo Workflows has a CLI and the installation instrucutions can be found [here](https://github.com/argoproj/argo-workflows/releases/).

Usage:

```bash
argo -n argo-events submit --from workflowtemplate/get-device-nautobot --parameter hostname=host.domain.local

Name:                get-device-nautobot-g5wlz
Namespace:           argo-events
ServiceAccount:      unset
Status:              Pending
Created:             Tue Apr 23 13:50:57 -0400 (now)
Progress:
Parameters:
  hostname:          host.domain.local
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
  hostname:          host.domain.local

STEP                          TEMPLATE           PODNAME  DURATION  MESSAGE
 ✔ get-device-nautobot-g5wlz  main
 └───✔ nautobot-query         nautobot-api/main
     └───✔ send-request       http
```

[argo-workflows]: <https://argo-workflows.readthedocs.io/en/latest/>
[argo-events]: <https://argoproj.github.io/argo-events/>
[argo-python]: <https://github.com/rackerlabs/understack/tree/main/argo-workflows/generic/code/argo_python>
