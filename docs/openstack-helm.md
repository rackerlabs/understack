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
apiVersion: mariadb.mmontes.io/v1alpha1
kind: Database
---
apiVersion: mariadb.mmontes.io/v1alpha1
kind: User
---
apiVersion: mariadb.mmontes.io/v1alpha1
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

[OSH]: <https://docs.openstack.org/openstack-helm/latest/>
[operator]: <https://kubernetes.io/docs/concepts/extend-kubernetes/operator/>
[mariadb-op]: <https://github.com/mariadb-operator/mariadb-operator>
[db-init]: <https://opendev.org/openstack/openstack-helm-infra/src/branch/master/helm-toolkit/templates/scripts/_db-init.py.tpl>
[db-drop]: <https://opendev.org/openstack/openstack-helm-infra/src/branch/master/helm-toolkit/templates/scripts/_db-drop.py.tpl>
