# Overview

The WorkflowTemplates provided in this directory were created to provide common lifecycle and maintenance functions on OBM controllers.

## Caveats

- TODO: the obm-sync-creds workflow logic should probably be broken to include an obm-update-password workflow, which then likely has more utility.

## Example
```bash
argo -n argo-events submit --from  workflowtemplate/obm-sync-creds --parameter hostname=host.domain.local

Name:                obm-sync-creds-wrn2c
Namespace:           argo-events
ServiceAccount:      unset
Status:              Pending
Created:             Tue Apr 23 14:24:07 -0400 (now)
Progress:
Parameters:
  hostname:          host.domain.local
```

```bash
argo -n argo-events get @latest
Name:                obm-sync-creds-wrn2c
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
  hostname:          host.domain.local

STEP                         TEMPLATE                 PODNAME                                         DURATION  MESSAGE
 ● obm-sync-creds-wrn2c      main
 ├─✔ get-obm-creds           get-obm-creds/main
 │ └─✔ get-obm-creds         get-obm-creds-ext/main
 │   └─✔ get-obm-creds-ext   get-creds-ext/main
 │     ├─✔ get-ext-num       get-ext-num/main
 │     └─✔ get-creds-ext     get-creds-ext           obm-sync-creds-wrn2c-get-creds-ext-2059517959  5s
 ├─✔ get-obm-ip              get-obm-ip/main
 │ └───✔ nautobot-query      nautobot-api/main
 │     └───✔ send-request    http
 └─◷ obm-sync-creds          obm-sync-creds           obm-sync-creds-wrn2c-obm-sync-creds-2727609696  28s
```
