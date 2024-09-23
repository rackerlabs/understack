# OpenStack Helm

The UnderStack project utilizes [OpenStack Helm][OSH] for many OpenStack
components, however we prefer to utilize upstream provided [operators][operator]
for infrastructure components. The [OpenStack Helm][OSH] project has
started to use some of them but has not fully embraced them yet.

## MariaDB

By utilizing the [MariaDB operator][mariadb-op] we're able to avoid the need
to run the [db-init][db-init] and [db-drop][db-drop] jobs by utilizing the
correct operator resources.

```yaml
apiVersion: k8s.mariadb.com/v1alpha1
kind: Database
---
apiVersion: k8s.mariadb.com/v1alpha1
kind: User
---
apiVersion: k8s.mariadb.com/v1alpha1
kind: Grant
```

The above resources, when configured do the following:

- create a database
- create a user
- grant permissions to a user on a database

Which is exactly what the [db-init][db-init] script does when executed
as a job. When these resources are deleted, the reverse operations
happen which is what the [db-drop][db-drop] script does. Lastly as these
scripts aren't used the associated `DB_CONNECTION` secret value isn't
necessary allowing us to disable the `secret_db` manifest.

More importantly, these two jobs rely on proper ordering via
[Helm Chart Hooks](https://helm.sh/docs/topics/charts_hooks/) which isn't
necessarily friendly towards GitOps.

## RabbitMQ

Similarly by utilizing RabbitMQ's [Cluster operator][cluster-op] and
[Messaging Topology operator][msg-top-op] we're able to avoid the
need for the [rabbit-init][rabbit-init] job by utilizing the correct
operator resources.

```yaml
apiVersion: rabbitmq.com/v1beta1
kind: Vhost
---
apiVersion: rabbitmq.com/v1beta1
kind: Queue
---
apiVersion: rabbitmq.com/v1beta1
kind: User
---
apiVersion: rabbitmq.com/v1beta1
kind: Permission
```

The above resources, when configured do the following:

- create a vhost
- create a queue in the vhost
- create a user
- grant permissions to a user on the queue in the vhost

Which is exactly what the [rabbit-init][rabbit-init] script does when executed
as a job. Lastly as these scripts aren't used the associated
`RABBITMQ_CONNECTION` secret value isn't necessary allowing us to disable the
`secret_rabbitmq` manifest.

[OSH]: <https://docs.openstack.org/openstack-helm/latest/>
[operator]: <https://kubernetes.io/docs/concepts/extend-kubernetes/operator/>
[mariadb-op]: <https://github.com/mariadb-operator/mariadb-operator>
[cluster-op]: <https://github.com/rabbitmq/cluster-operator>
[msg-top-op]: <https://github.com/rabbitmq/messaging-topology-operator>
[db-init]: <https://opendev.org/openstack/openstack-helm-infra/src/branch/master/helm-toolkit/templates/scripts/_db-init.py.tpl>
[db-drop]: <https://opendev.org/openstack/openstack-helm-infra/src/branch/master/helm-toolkit/templates/scripts/_db-drop.py.tpl>
[rabbit-init]: <https://opendev.org/openstack/openstack-helm-infra/src/branch/master/helm-toolkit/templates/scripts/_rabbit-init.sh.tpl>
