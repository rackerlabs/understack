# Overview

The WorkflowTemplates provided in this directory were created to provide common lifecycle and maintenance functions on BMC controllers.

## Caveats

- TODO: the bmc-sync-creds workflow logic should probably be broken to include a bmc-update-password workflow, which then likely has more utility.

## Example
```bash
argo -n argo-events submit --from  workflowtemplate/bmc-sync-creds --parameter device_id=1de4f169-9848-4d8e-921b-65338c1e00ca

Name:                bmc-sync-creds-wrn2c
Namespace:           argo-events
ServiceAccount:      unset
Status:              Pending
Created:             Tue Apr 23 14:24:07 -0400 (now)
Progress:
Parameters:
  device_id:         1de4f169-9848-4d8e-921b-65338c1e00ca
```

```bash
argo -n argo-events get @latest
Name:                bmc-sync-creds-wrn2c
Namespace:           argo-events
ServiceAccount:      workflow
Status:              Running
Conditions:
 PodRunning          False
Created:             Tue Apr 23 14:24:07 -0400 (58 seconds ago)
Started:             Tue Apr 23 14:24:07 -0400 (58 seconds ago)
Duration:            58 seconds
Progress:            2/3
ResourcesDuration:   0s*(1 cpu),5s*(100Mi memory)
Parameters:
  device_id:         1de4f169-9848-4d8e-921b-65338c1e00ca

STEP                         TEMPLATE                 PODNAME                                         DURATION  MESSAGE
 ● bmc-sync-creds-wrn2c      main
 ├─✔ get-bmc-creds           get-bmc-creds/main
 │ └─✔ get-bmc-creds         get-bmc-creds-ext/main
 │   └─✔ get-bmc-creds-ext   get-creds-ext/main
 │     ├─✔ get-ext-num       get-ext-num/main
 │     └─✔ get-creds-ext     get-creds-ext           bmc-sync-creds-wrn2c-get-creds-ext-2059517959  5s
 ├─✔ get-bmc-ip              get-bmc-ip/main
 │ └───✔ nautobot-query      nautobot-api/main
 │     └───✔ send-request    http
 └─◷ bmc-sync-creds          bmc-sync-creds           bmc-sync-creds-wrn2c-bmc-sync-creds-2727609696  28s
```
