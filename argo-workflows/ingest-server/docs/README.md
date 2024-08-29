

# Overview

This workflow ingests a server in to Understack.

Create the workflows manually:

``` bash
argo template create *.yaml
```

Create a job with the new workflow:

``` bash
argo submit --watch --serviceaccount workflow --from workflowtemplate/ingest-server -p interface_update_event=value1 -p hostname=node1
```
