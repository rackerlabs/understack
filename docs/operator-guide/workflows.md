# Argo Workflows

Upstream docs: <https://argoproj.github.io/workflows/>

## Troubleshooting

### Cleaning up failed and errored workflows

When an argo workflow fails, the failed workflow remains in argo until it's cleaned up.
If prometheus monitoring is enabled (it's enabled by default in understack), prometheus
will fire alerts which look like this:

``` text
[FIRING:4] argo-events (monitoring/kube-prometheus-stack-prometheus)
Alerts Firing:
Labels:
alertname = KubePodNotReady
namespace = argo-events
pod = keystone-event-project-4ksc7
prometheus = monitoring/kube-prometheus-stack-prometheus
severity = warning
Annotations:
description = Pod argo-events/keystone-event-project-4ksc7 has been in a non-ready state for longer than 15 minutes.
```

We can then examine the argo workflow logs and kubernetes pod logs to investigate
and resolve the failure reasons.

Once we are done investigating, we can clean up the failed and error workflows,
which will resolve the prometheus alerts and delete the errored kubernetes pods
for the workflows.

Find the problem argo workflows:

``` bash
argo -n argo-events list --status Failed,Error
```

We should see something like this:

``` bash
  argo -n argo-events list --status Failed,Error
NAME                           STATUS   AGE   DURATION   PRIORITY   MESSAGE
enroll-server-zd4mr            Failed   21m   1m         0          child 'enroll-server-zd4mr-3808326199' failed
enroll-server-rgjtv            Failed   21m   1m         0          child 'enroll-server-rgjtv-2375211231' failed
enroll-server-mztsg            Failed   21m   1m         0          child 'enroll-server-mztsg-2423736745' failed
enroll-server-7cbvl            Failed   1h    1m         0          child 'enroll-server-7cbvl-3643463660' failed
enroll-server-k7mmt            Failed   1h    1m         0          child 'enroll-server-k7mmt-2823679138' failed
enroll-server-q56x9            Failed   1h    1m         0          child 'enroll-server-q56x9-488690725' failed
ironic-node-update-wx6gk       Failed   2h    10s        0          Error (exit code 1)
ironic-node-update-4xxtn       Failed   2h    10s        0          Error (exit code 1)
ironic-node-update-b5m6l       Failed   2h    10s        0          Error (exit code 1)
ironic-node-update-j649b       Failed   2h    10s        0          Error (exit code 1)
ironic-node-update-rswvq       Failed   2h    10s        0          Error (exit code 1)
ironic-node-update-kk5sf       Failed   19h   10s        0          Error (exit code 1)
ironic-node-update-wl2n7       Failed   19h   10s        0          Error (exit code 1)
ironic-node-update-jd727       Failed   19h   10s        0          Error (exit code 1)
keystone-event-project-zjnzv   Failed   1d    10s        0          Error (exit code 1)
keystone-event-project-6gxzn   Failed   1d    10s        0          Error (exit code 1)
keystone-event-project-45jf9   Failed   1d    10s        0          Error (exit code 1)
keystone-event-project-pxcxg   Failed   1d    10s        0          Error (exit code 1)
keystone-event-project-mtl4s   Error    45d   21s        0          Error (exit code 1): pods "keystone-event-project-mtl4s" is forbidden: User "system:serviceaccount:argo-events:default" cannot patch resource "pods" in API group "" in the namespace "argo-events"
```

You can delete a single workflow:

``` bash
argo -n argo-events delete $workflow
```

For example:

``` bash
argo -n argo-events delete enroll-server-zd4mr
```

With a simple for loop we can delete all the failed and errored workflows:

``` bash
for workflow in `argo -n argo-events list --status Failed,Error | egrep "Failed|Error" | awk '{print $1}'`; do
    argo -n argo-events delete $workflow ;
done
```
