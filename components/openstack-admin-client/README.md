# OpenStack Admin

Deploys a pod with the `openstack` cli client.

## Enter the openstack-admin-client pod

```bash
kubectl exec -it openstack-admin-client -- /bin/bash
```

## Run openstack CLI commands

Inside the openstack-admin-client pod, you can run `openstack` CLI commands as you would normally.

For example, list the endpoints:

```bash
root@openstack-admin-client:/# openstack endpoint list
+----------------------------------+-----------+--------------+--------------+---------+-----------+---------------------------------------------------------+
| ID                               | Region    | Service Name | Service Type | Enabled | Interface | URL                                                     |
+----------------------------------+-----------+--------------+--------------+---------+-----------+---------------------------------------------------------+
| 48e41a5730084757817152777b3fcd46 | RegionOne | keystone     | identity     | True    | admin     | http://keystone.openstack.svc.cluster.local/v3          |
| 4e9e0e7959ee4febb309ab0b6e1d56e0 | RegionOne | ironic       | baremetal    | True    | admin     | http://ironic-api.openstack.svc.cluster.local:6385/     |
| 882e744ef06a4e908ce69e2e8f43d000 | RegionOne | keystone     | identity     | True    | internal  | http://keystone-api.openstack.svc.cluster.local:5000/v3 |
| b5afc67939fc47dcb051e33ce8bbab61 | RegionOne | ironic       | baremetal    | True    | internal  | http://ironic-api.openstack.svc.cluster.local:6385/     |
+----------------------------------+-----------+--------------+--------------+---------+-----------+---------------------------------------------------------+
```

List users:

```bash
root@openstack-admin-client:/# openstack user list
+----------------------------------+-------+
| ID                               | Name  |
+----------------------------------+-------+
| 46dfcca224744e6d84347257d7b889ae | admin |
| a8bdbad5667d4d6ba905d14db34cf825 | demo  |
+----------------------------------+-------+
```

List groups:

```bash
root@openstack-admin-client:/# openstack group list
+----------------------------------+---------+
| ID                               | Name    |
+----------------------------------+---------+
| d14666f813da4f4894392e829ad6a96f | dctech  |
| 2815d7b9b7be4b00a96ca31b690e6441 | ucadmin |
| 379c2dc598a3432eb28f0fe842e83624 | user    |
+----------------------------------+---------+
```

Get admin user's token:

```bash
# print out the admin token
openstack token issue
```

Or you can export the admin token as `TOKEN` variable, useful for scripting:

```bash
# extract and export the admin token as TOKEN variable
export TOKEN=$(openstack token issue -f json | jq -r '.id')
```
