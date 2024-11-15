# Argo Workflows

[Argo Workflows][argo-workflows] was chosen as our workflow / orchestration service. It runs natively inside a
Kubernetes environment and easily integrates with [Argo Events][argo-events]. Understack will be deployed with the
set of WorkflowTemplates below.

## WorkflowTemplates

| WorkflowTemplate      | Description                                               | Input                   | Output     |   |
|---------------------- |-----------------------------------------------------------|-------------------------|------------|---|
| get-device-nautobot   | Return Device Information from Nautobot                   | device_id               | device     |   |
| get-bmc-creds         | Get the credentials for the target Device                 | device_id               | secret     | * |
| get-bmc-ip            | Get BMC IP address for target Device                      | device_id               | ip         |   |
| nautobot-api          | HTTP Template Workflow to query the Nautobot API          | method,nautobot_url,uri | result     |   |
| bmc-sync-creds        | Sync's a devices BMC password with what we have on record | device_id               |            |   |

\* WorkflowTemplate which requires a manual / custom implementation.

As Understack develops, there may be underlying / dependant services which are not included, and require some of the
included WorkflowTemplates to be manually implemented to work in your environment. For example, the get-bmc-creds
WorkflowTemplate will need to be written to communicate with whatever service you're using to store your device
credentials.

## Setup

The included Workflows include references to configuration ConfigMaps and Secrets.

### Nautobot

The Secret will be defined by the External Secret.

```bash
kubectl -n argo create configmap nautobot '--from-literal=url=https://nautobot.local'
```

## Security

Authorization is handled by Kubernetes' RBAC services. Workflows are run with the context of a given Kubernetes Service
Account. We've provided the `workflow` Service Account, which has been granted access to the necessary Kubernetes
resources, to run the provided WorkflowTemplates.

### Argo CLI

Argo Workflows has a CLI and the installation instructions can be found [here](https://github.com/argoproj/argo-workflows/releases/).

Usage:

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

[argo-workflows]: <https://argo-workflows.readthedocs.io/en/latest/>
[argo-events]: <https://argoproj.github.io/argo-events/>
