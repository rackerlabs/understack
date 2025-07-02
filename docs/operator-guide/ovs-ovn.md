---
render_macros: false
---

# OVN / Open vSwitch

## Debugging OVN / Open vSwitch

To troubleshoot OVN specific issues you'll want to refer to
the [OVN manual pages](https://docs.ovn.org/en/latest/ref/index.html).

To troubleshoot OVS specific issues you'll want to refer to
the [OVS manual pages](https://docs.openvswitch.org/en/latest/ref/#man-pages).

The `ovn-` prefixed commands can be run from the `ovn-` prefixed pods.
Specifically the north and south DB pods will have the most best data.

The `ovs-` prefixed commands should be run from the `openvswitch` pods.

## Troubleshooting alert NeutronAgentDown

If you see this prometheus alert, the following steps may help to resolve the issue.

``` text
name: NeutronAgentDown
expr: openstack_neutron_agent_state != 1
labels:
severity: P4
annotations:
description: The service `{{$labels.exported_service}}` running on `{{$labels.hostname}}` is being reported as down.
summary: [`{{$labels.hostname}}`] `{{$labels.exported_service}}` down
```

First, check the neutron agent statuses:

``` text
 openstack network agent list
+--------------------------------------+------------------------------+--------------------------------------+-------------------+-------+-------+----------------------+
| ID                                   | Agent Type                   | Host                                 | Availability Zone | Alive | State | Binary               |
+--------------------------------------+------------------------------+--------------------------------------+-------------------+-------+-------+----------------------+
| 00a833c1-7395-438c-956d-76a68c363992 | Baremetal Node               | b31cd289-c475-481d-b34b-ca52106a9222 | None              | XXX   | UP    | ironic-neutron-agent |
| 0c292b05-73b8-4851-9fca-23343e51d75e | Baremetal Node               | 3a4f592b-c5f2-4df2-85dd-a8a810856b55 | None              | XXX   | UP    | ironic-neutron-agent |
| 136f56f2-fc81-482d-b461-261df5d1c59b | Baremetal Node               | 113752b7-489a-4206-b2a1-e4fcbed8d6d7 | None              | XXX   | UP    | ironic-neutron-agent |
| 1b2e3104-3596-4544-a535-35a64f2c61cb | Baremetal Node               | 61694efc-0834-4b3f-b10d-e7534ece1d7c | None              | XXX   | UP    | ironic-neutron-agent |
| 21ceeba6-4370-4bca-9b90-fc403b9dd325 | Baremetal Node               | a1a61c02-7df2-4e5b-b8fe-b0fb115b2885 | None              | XXX   | UP    | ironic-neutron-agent |
| 31c472d9-fde7-4354-95d4-d4a6b287a65f | Baremetal Node               | 29fb8908-a225-4bda-a5c7-ea9c8d80df97 | None              | XXX   | UP    | ironic-neutron-agent |
| 391f2b35-1904-4a51-a91a-0b94efbaeae1 | Baremetal Node               | 5ae6258c-255e-4d5c-9a6e-2048b914e516 | None              | XXX   | UP    | ironic-neutron-agent |
| 40228bd2-dbed-4efd-99fd-1b25f73c5486 | Baremetal Node               | 063fcc5c-5d7d-42cb-8f53-20284eb6e553 | None              | XXX   | UP    | ironic-neutron-agent |
| 483cb4c6-282e-45e0-a2c8-aab8d73251c0 | Baremetal Node               | f6be9302-96b0-47e9-ad63-6056a5e9a8f5 | None              | XXX   | UP    | ironic-neutron-agent |
| 67412731-8a9d-4045-9fb3-dc8c74739c0e | Baremetal Node               | 6cc75fc1-756a-4b19-bbab-fe8e63eee45b | None              | XXX   | UP    | ironic-neutron-agent |
| 6cb9a276-6d51-4d7f-81b3-75d4822ae9df | Baremetal Node               | f6293c81-49ff-40ff-baed-9833f6bf7480 | None              | XXX   | UP    | ironic-neutron-agent |
| 81abb06b-176c-4248-bbcf-690d794c837b | Baremetal Node               | de6495fc-3df2-4724-8217-5745d679fad1 | None              | XXX   | UP    | ironic-neutron-agent |
| 90b18cc3-ae2f-45f7-a558-9ac00ca5b280 | Baremetal Node               | bfa06d8a-7d2e-4934-aeb5-c9b185b83548 | None              | XXX   | UP    | ironic-neutron-agent |
| 944cf411-5c22-45d7-a057-8b4eff338e7b | Baremetal Node               | 0572c9c4-8199-4d34-957f-4c3fb310d557 | None              | XXX   | UP    | ironic-neutron-agent |
| 95807c35-d58c-4a40-bf59-61173a41dcc1 | Baremetal Node               | b9f80d94-aa2b-4f0c-ae4a-2f5e5dfaad25 | None              | XXX   | UP    | ironic-neutron-agent |
| a451c2bd-e2fb-4c24-8105-235eb40d8a48 | Baremetal Node               | b68bd2fb-8670-4205-b9e9-737de89dfcba | None              | XXX   | UP    | ironic-neutron-agent |
| aa2ce8d4-2f47-4e0a-8b94-428f65fec2e0 | Baremetal Node               | 7102d86d-2f7b-4217-8653-d5a8e8957a7c | None              | XXX   | UP    | ironic-neutron-agent |
| ab01ce9a-0b7e-49c8-8c85-ece612e30cbc | Baremetal Node               | 048e3b73-9c5e-4727-a36b-a00406212aa0 | None              | XXX   | UP    | ironic-neutron-agent |
| b43072a9-d20c-4800-a29f-d0f761c0cd31 | Baremetal Node               | 90b75aae-bd7b-4ad8-98f0-230968738d2c | None              | XXX   | UP    | ironic-neutron-agent |
| c794a5f1-fca9-4862-8841-4577eeaa0d1f | Baremetal Node               | 2e32caa9-482a-4ca1-a16b-3dcc164e696c | None              | XXX   | UP    | ironic-neutron-agent |
| e7c44284-7b02-4193-bd8e-ec37684dca57 | Baremetal Node               | 61a7f7b9-ec6a-4250-a096-fea2b954d9be | None              | XXX   | UP    | ironic-neutron-agent |
| ec9cf408-355c-4d13-acc3-fa86dc4a99af | Baremetal Node               | 4933fb3d-aa7c-4569-ae25-0af879a11291 | None              | XXX   | UP    | ironic-neutron-agent |
| f57317ec-8bb0-47f3-bfbc-31cb4c09a9b1 | Baremetal Node               | ce27f4a5-9607-41f4-b48d-f6b5ae88da88 | None              | XXX   | UP    | ironic-neutron-agent |
| 10669d82-03c7-450f-8b0d-32acc75fc987 | OVN Controller Gateway agent | 1327172-hp1                          |                   | XXX   | UP    | ovn-controller       |
+--------------------------------------+------------------------------+--------------------------------------+-------------------+-------+-------+----------------------+
```

All the agents are reporting as down with `XXX` in the Alive column. This likely means either the ovn controller is having an issue,
the ironic neutron agent is having an issue, or both of those services are having issues.

Looking at the neutron-ironic-agent logs we don't see any obvious errors:

``` text
 kubectl logs -f neutron-ironic-agent-764fd4dcd6-szzd5
Defaulted container "neutron-ironic-agent" out of: neutron-ironic-agent, init (init)
+ COMMAND=start
+ start
+ exec ironic-neutron-agent --config-file /etc/neutron/neutron.conf --config-file /etc/neutron/plugins/ml2/ml2_conf.ini
2025-04-14 15:50:20.721 1 INFO neutron.common.config [-] Logging enabled!
2025-04-14 15:50:20.721 1 INFO neutron.common.config [-] /var/lib/openstack/bin/ironic-neutron-agent version 24.1.1.dev41
```

But looking at the ovn-controller logs shows a problem:

``` text
2025-04-14T15:31:35.834Z|00313|ovsdb_idl|WARN|transaction error: {"details":"Transaction causes multiple rows in \"Encap\" table to have identical values (geneve and \"10.46.100.84\") for index on columns \"type\" and \"ip\".  First row, with UUID 859dad94-3322-41ae-af23-893cdc474aba, existed in the database before this transaction and was not modified by the transaction.  Second row, with UUID 37a9d58a-4848-4578-bf8b-58da6ab81972, was inserted by this transaction.","error":"constraint violation"}
2025-04-14T15:31:35.834Z|00314|main|INFO|OVNSB commit failed, force recompute next time.
```

The transaction fails due to duplicate rows, which can occur if the hostname of the ovn-controller changes, amongst other reasons.

We can fix this issue by deleting the old chassis from ovn, restarting the ovn-controller service, and then restarting the
neutron ironic agent service.

Fix ovn data:

``` text
 kubectl exec -it ovn-ovsdb-sb-0 -- bash
Defaulted container "ovsdb" out of: ovsdb, init (init)
root@ovn-ovsdb-sb-0:/# ovn-sbctl list encap
_uuid               : 859dad94-3322-41ae-af23-893cdc474aba
chassis_name        : "10669d82-03c7-450f-8b0d-32acc75fc987"
ip                  : "10.46.100.84"
options             : {csum="true"}
type                : geneve
root@ovn-ovsdb-sb-0:/# ovn-sbctl chassis-del 10669d82-03c7-450f-8b0d-32acc75fc987
```

Restart ovn-controller:

``` text
 kubectl rollout restart daemonset ovn-controller
daemonset.apps/ovn-controller restarted
```

Check the ovn-controller logs and the duplicate key error should be gone now.

Once ovn-controller has finished restarting, then restart the neutron ironic agent:

``` text
 kubectl rollout restart deployment neutron-ironic-agent
deployment.apps/neutron-ironic-agent restarted
```

Give it a moment to restart and perform re-checks of the agents, and we should see healthy network agents now:

``` text
 openstack network agent list
+--------------------------------------+------------------------------+--------------------------------------+-------------------+-------+-------+----------------------+
| ID                                   | Agent Type                   | Host                                 | Availability Zone | Alive | State | Binary               |
+--------------------------------------+------------------------------+--------------------------------------+-------------------+-------+-------+----------------------+
| 00a833c1-7395-438c-956d-76a68c363992 | Baremetal Node               | b31cd289-c475-481d-b34b-ca52106a9222 | None              | :-)   | UP    | ironic-neutron-agent |
| 0c292b05-73b8-4851-9fca-23343e51d75e | Baremetal Node               | 3a4f592b-c5f2-4df2-85dd-a8a810856b55 | None              | :-)   | UP    | ironic-neutron-agent |
| 136f56f2-fc81-482d-b461-261df5d1c59b | Baremetal Node               | 113752b7-489a-4206-b2a1-e4fcbed8d6d7 | None              | :-)   | UP    | ironic-neutron-agent |
| 1b2e3104-3596-4544-a535-35a64f2c61cb | Baremetal Node               | 61694efc-0834-4b3f-b10d-e7534ece1d7c | None              | :-)   | UP    | ironic-neutron-agent |
| 21ceeba6-4370-4bca-9b90-fc403b9dd325 | Baremetal Node               | a1a61c02-7df2-4e5b-b8fe-b0fb115b2885 | None              | :-)   | UP    | ironic-neutron-agent |
| 31c472d9-fde7-4354-95d4-d4a6b287a65f | Baremetal Node               | 29fb8908-a225-4bda-a5c7-ea9c8d80df97 | None              | :-)   | UP    | ironic-neutron-agent |
| 391f2b35-1904-4a51-a91a-0b94efbaeae1 | Baremetal Node               | 5ae6258c-255e-4d5c-9a6e-2048b914e516 | None              | :-)   | UP    | ironic-neutron-agent |
| 40228bd2-dbed-4efd-99fd-1b25f73c5486 | Baremetal Node               | 063fcc5c-5d7d-42cb-8f53-20284eb6e553 | None              | :-)   | UP    | ironic-neutron-agent |
| 483cb4c6-282e-45e0-a2c8-aab8d73251c0 | Baremetal Node               | f6be9302-96b0-47e9-ad63-6056a5e9a8f5 | None              | :-)   | UP    | ironic-neutron-agent |
| 67412731-8a9d-4045-9fb3-dc8c74739c0e | Baremetal Node               | 6cc75fc1-756a-4b19-bbab-fe8e63eee45b | None              | :-)   | UP    | ironic-neutron-agent |
| 6cb9a276-6d51-4d7f-81b3-75d4822ae9df | Baremetal Node               | f6293c81-49ff-40ff-baed-9833f6bf7480 | None              | :-)   | UP    | ironic-neutron-agent |
| 81abb06b-176c-4248-bbcf-690d794c837b | Baremetal Node               | de6495fc-3df2-4724-8217-5745d679fad1 | None              | :-)   | UP    | ironic-neutron-agent |
| 90b18cc3-ae2f-45f7-a558-9ac00ca5b280 | Baremetal Node               | bfa06d8a-7d2e-4934-aeb5-c9b185b83548 | None              | :-)   | UP    | ironic-neutron-agent |
| 944cf411-5c22-45d7-a057-8b4eff338e7b | Baremetal Node               | 0572c9c4-8199-4d34-957f-4c3fb310d557 | None              | :-)   | UP    | ironic-neutron-agent |
| 95807c35-d58c-4a40-bf59-61173a41dcc1 | Baremetal Node               | b9f80d94-aa2b-4f0c-ae4a-2f5e5dfaad25 | None              | :-)   | UP    | ironic-neutron-agent |
| a451c2bd-e2fb-4c24-8105-235eb40d8a48 | Baremetal Node               | b68bd2fb-8670-4205-b9e9-737de89dfcba | None              | :-)   | UP    | ironic-neutron-agent |
| aa2ce8d4-2f47-4e0a-8b94-428f65fec2e0 | Baremetal Node               | 7102d86d-2f7b-4217-8653-d5a8e8957a7c | None              | :-)   | UP    | ironic-neutron-agent |
| ab01ce9a-0b7e-49c8-8c85-ece612e30cbc | Baremetal Node               | 048e3b73-9c5e-4727-a36b-a00406212aa0 | None              | :-)   | UP    | ironic-neutron-agent |
| b43072a9-d20c-4800-a29f-d0f761c0cd31 | Baremetal Node               | 90b75aae-bd7b-4ad8-98f0-230968738d2c | None              | :-)   | UP    | ironic-neutron-agent |
| c794a5f1-fca9-4862-8841-4577eeaa0d1f | Baremetal Node               | 2e32caa9-482a-4ca1-a16b-3dcc164e696c | None              | :-)   | UP    | ironic-neutron-agent |
| e7c44284-7b02-4193-bd8e-ec37684dca57 | Baremetal Node               | 61a7f7b9-ec6a-4250-a096-fea2b954d9be | None              | :-)   | UP    | ironic-neutron-agent |
| ec9cf408-355c-4d13-acc3-fa86dc4a99af | Baremetal Node               | 4933fb3d-aa7c-4569-ae25-0af879a11291 | None              | :-)   | UP    | ironic-neutron-agent |
| f57317ec-8bb0-47f3-bfbc-31cb4c09a9b1 | Baremetal Node               | ce27f4a5-9607-41f4-b48d-f6b5ae88da88 | None              | :-)   | UP    | ironic-neutron-agent |
| 10669d82-03c7-450f-8b0d-32acc75fc987 | OVN Controller Gateway agent | 1327172-hp1                          |                   | XXX   | UP    | ovn-controller       |
| a2172b59-5558-4018-858d-88947e2d9adf | OVN Controller Gateway agent | 1327172-hp1                          |                   | :-)   | UP    | ovn-controller       |
+--------------------------------------+------------------------------+--------------------------------------+-------------------+-------+-------+----------------------+
```

We can delete the old ovn controller network agent to clean it up:

``` text
 openstack network agent delete 10669d82-03c7-450f-8b0d-32acc75fc987
```

Now everything is back to normal and the prometheus alert should clear:

``` text
 openstack network agent list
+--------------------------------------+------------------------------+--------------------------------------+-------------------+-------+-------+----------------------+
| ID                                   | Agent Type                   | Host                                 | Availability Zone | Alive | State | Binary               |
+--------------------------------------+------------------------------+--------------------------------------+-------------------+-------+-------+----------------------+
| 00a833c1-7395-438c-956d-76a68c363992 | Baremetal Node               | b31cd289-c475-481d-b34b-ca52106a9222 | None              | :-)   | UP    | ironic-neutron-agent |
| 0c292b05-73b8-4851-9fca-23343e51d75e | Baremetal Node               | 3a4f592b-c5f2-4df2-85dd-a8a810856b55 | None              | :-)   | UP    | ironic-neutron-agent |
| 136f56f2-fc81-482d-b461-261df5d1c59b | Baremetal Node               | 113752b7-489a-4206-b2a1-e4fcbed8d6d7 | None              | :-)   | UP    | ironic-neutron-agent |
| 1b2e3104-3596-4544-a535-35a64f2c61cb | Baremetal Node               | 61694efc-0834-4b3f-b10d-e7534ece1d7c | None              | :-)   | UP    | ironic-neutron-agent |
| 21ceeba6-4370-4bca-9b90-fc403b9dd325 | Baremetal Node               | a1a61c02-7df2-4e5b-b8fe-b0fb115b2885 | None              | :-)   | UP    | ironic-neutron-agent |
| 31c472d9-fde7-4354-95d4-d4a6b287a65f | Baremetal Node               | 29fb8908-a225-4bda-a5c7-ea9c8d80df97 | None              | :-)   | UP    | ironic-neutron-agent |
| 391f2b35-1904-4a51-a91a-0b94efbaeae1 | Baremetal Node               | 5ae6258c-255e-4d5c-9a6e-2048b914e516 | None              | :-)   | UP    | ironic-neutron-agent |
| 40228bd2-dbed-4efd-99fd-1b25f73c5486 | Baremetal Node               | 063fcc5c-5d7d-42cb-8f53-20284eb6e553 | None              | :-)   | UP    | ironic-neutron-agent |
| 483cb4c6-282e-45e0-a2c8-aab8d73251c0 | Baremetal Node               | f6be9302-96b0-47e9-ad63-6056a5e9a8f5 | None              | :-)   | UP    | ironic-neutron-agent |
| 67412731-8a9d-4045-9fb3-dc8c74739c0e | Baremetal Node               | 6cc75fc1-756a-4b19-bbab-fe8e63eee45b | None              | :-)   | UP    | ironic-neutron-agent |
| 6cb9a276-6d51-4d7f-81b3-75d4822ae9df | Baremetal Node               | f6293c81-49ff-40ff-baed-9833f6bf7480 | None              | :-)   | UP    | ironic-neutron-agent |
| 81abb06b-176c-4248-bbcf-690d794c837b | Baremetal Node               | de6495fc-3df2-4724-8217-5745d679fad1 | None              | :-)   | UP    | ironic-neutron-agent |
| 90b18cc3-ae2f-45f7-a558-9ac00ca5b280 | Baremetal Node               | bfa06d8a-7d2e-4934-aeb5-c9b185b83548 | None              | :-)   | UP    | ironic-neutron-agent |
| 944cf411-5c22-45d7-a057-8b4eff338e7b | Baremetal Node               | 0572c9c4-8199-4d34-957f-4c3fb310d557 | None              | :-)   | UP    | ironic-neutron-agent |
| 95807c35-d58c-4a40-bf59-61173a41dcc1 | Baremetal Node               | b9f80d94-aa2b-4f0c-ae4a-2f5e5dfaad25 | None              | :-)   | UP    | ironic-neutron-agent |
| a451c2bd-e2fb-4c24-8105-235eb40d8a48 | Baremetal Node               | b68bd2fb-8670-4205-b9e9-737de89dfcba | None              | :-)   | UP    | ironic-neutron-agent |
| aa2ce8d4-2f47-4e0a-8b94-428f65fec2e0 | Baremetal Node               | 7102d86d-2f7b-4217-8653-d5a8e8957a7c | None              | :-)   | UP    | ironic-neutron-agent |
| ab01ce9a-0b7e-49c8-8c85-ece612e30cbc | Baremetal Node               | 048e3b73-9c5e-4727-a36b-a00406212aa0 | None              | :-)   | UP    | ironic-neutron-agent |
| b43072a9-d20c-4800-a29f-d0f761c0cd31 | Baremetal Node               | 90b75aae-bd7b-4ad8-98f0-230968738d2c | None              | :-)   | UP    | ironic-neutron-agent |
| c794a5f1-fca9-4862-8841-4577eeaa0d1f | Baremetal Node               | 2e32caa9-482a-4ca1-a16b-3dcc164e696c | None              | :-)   | UP    | ironic-neutron-agent |
| e7c44284-7b02-4193-bd8e-ec37684dca57 | Baremetal Node               | 61a7f7b9-ec6a-4250-a096-fea2b954d9be | None              | :-)   | UP    | ironic-neutron-agent |
| ec9cf408-355c-4d13-acc3-fa86dc4a99af | Baremetal Node               | 4933fb3d-aa7c-4569-ae25-0af879a11291 | None              | :-)   | UP    | ironic-neutron-agent |
| f57317ec-8bb0-47f3-bfbc-31cb4c09a9b1 | Baremetal Node               | ce27f4a5-9607-41f4-b48d-f6b5ae88da88 | None              | :-)   | UP    | ironic-neutron-agent |
| a2172b59-5558-4018-858d-88947e2d9adf | OVN Controller Gateway agent | 1327172-hp1                          |                   | :-)   | UP    | ovn-controller       |
+--------------------------------------+------------------------------+--------------------------------------+-------------------+-------+-------+----------------------+
```

## Resync Neutron with OVN

Resync neutron data with OVN and repair the ovn database by running the
`neutron-ovn-db-sync-util` command in a neutron-server pod:

``` text
kubectl -n openstack exec -it neutron-server-7f798ff5cd-bhj5q -- neutron-ovn-db-sync-util \
    --ovn-neutron_sync_mode \
    repair \
    --config-file /etc/neutron/neutron.conf \
    --config-file /etc/neutron/plugins/ml2/ml2_conf.ini \
    --debug
```
