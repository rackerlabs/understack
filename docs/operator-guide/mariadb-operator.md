# MariaDB Operator

Useful commands for working with the MariaDB operator.

Docs: <https://github.com/mariadb-operator/mariadb-operator/blob/main/docs/README.md>

Repo: <https://github.com/mariadb-operator/mariadb-operator>

## Connect to MariaDB for OpenStack as root user

Create a port forward on your local machine to the OpenStack MariaDB server pod:

```bash
kubectl -n openstack port-forward mariadb-0 3306:3306
```

(MacOS) Connect to the database from your Mac using the `brew install mariadb` client:

```bash
# extract root password from the kubernetes secret, then connect
ROOTPASSWORD=$(kubectl get secret -n openstack mariadb -o json | jq -r '.data["root-password"]' | base64 -d) /usr/local/opt/mariadb/bin/mariadb -h 127.0.0.1 --skip-ssl -u root --password=$ROOTPASSWORD
```

## Dump a MariaDB database

Create a port forward on your local machine to the OpenStack MariaDB server pod:

```bash
kubectl -n openstack port-forward mariadb-0 3306:3306
```

(MacOS) Dump the database from your Mac using the `brew install mariadb` client:

```bash
# specify the db to dump
DB_TO_DUMP=ironic
#extract root password from the kubernetes secret
ROOTPASSWORD=$(kubectl get secret -n openstack mariadb -o json | jq -r '.data["root-password"]' | base64 -d)
# perform the db dump
/usr/local/opt/mariadb/bin/mariadb-dump -h 127.0.0.1 --skip-ssl -u root --password=$ROOTPASSWORD $DB_TO_DUMP | gzip > $DB_TO_DUMP.sql.gz
```

## Manual backup to a local .sql file

``` bash
kubectl exec -n openstack -it mariadb-0 -- mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" \
  --single-transaction \
  --routines \
  --triggers \
  --all-databases > full-backup-$(date +%Y%m%d-%H%M).sql
```

## Logical backup

1. Create a MariaDB Operator backup manifest. In this example we'll call it `create-mariadb-backup.yaml`

``` bash
apiVersion: k8s.mariadb.com/v1alpha1
kind: Backup
metadata:
  name: backup-pre-upgrade
spec:
  mariaDbRef:
    name: mariadb
  storage:
    persistentVolumeClaim:
      resources:
        requests:
          storage: 20Gi
      accessModes:
        - ReadWriteOnce
```

1. Apply the manifest:

``` bash
$ kubectl apply -f create-mariadb-backup.yaml
backup.k8s.mariadb.com/backup-pre-upgrade created
```

1. Check and wait until the backup has been completed:

``` bash
$ kubectl get backup.k8s.mariadb.com/backup-pre-upgrade
NAME                 COMPLETE   STATUS    MARIADB   AGE
backup-pre-upgrade   True       Success   mariadb   26s
```

``` bash
$ kubectl describe backup.k8s.mariadb.com/backup-pre-upgrade
Name:         backup-pre-upgrade
Namespace:    openstack
Labels:       <none>
Annotations:  <none>
API Version:  k8s.mariadb.com/v1alpha1
Kind:         Backup
Metadata:
  Creation Timestamp:  2025-10-21T14:19:28Z
  Generation:          2
  Resource Version:    299003488
  UID:                 6f1481c0-9cc6-46c3-98c4-e64390b09aed
Spec:
  Backoff Limit:       5
  Compression:         none
  Ignore Global Priv:  true
  Log Level:           info
  Maria Db Ref:
    Name:                mariadb
    Wait For It:         true
  Max Retention:         720h0m0s
  Restart Policy:        OnFailure
  Service Account Name:  backup-pre-upgrade
  Storage:
    Persistent Volume Claim:
      Access Modes:
        ReadWriteOnce
      Resources:
        Requests:
          Storage:  20Gi
Status:
  Conditions:
    Last Transition Time:  2025-10-21T14:19:38Z
    Message:               Success
    Reason:                JobComplete
    Status:                True
    Type:                  Complete
Events:                    <none>
```

## Restore from a point in time backup

This assumes you have backups enabled with regularly scheduled backups: <https://github.com/mariadb-operator/mariadb-operator/blob/main/docs/BACKUP.md/#scheduling>

Create a manifest with a point in time to restore from:

``` yaml
apiVersion: k8s.mariadb.com/v1alpha1
kind: Restore
metadata:
  name: restore
spec:
  mariaDbRef:
    name: mariadb
  backupRef:
    name: backup
  targetRecoveryTime: 2025-03-13T09:00:00Z
```

Apply the manifest:

``` text
 kubectl apply -f restore-time.yaml
restore.k8s.mariadb.com/restore created
```

Check the status:

``` text
 kubectl get restore
NAME      COMPLETE   STATUS    MARIADB   AGE
restore   False      Running   mariadb   4s
```

Watch the restore logs:

``` text
 kubectl logs -f restore-jtd9x
Defaulted container "mariadb" out of: mariadb, mariadb-operator (init)
💾 Restoring backup: /backup/backup.2025-03-13T09:00:05Z.sql
```

## Inspecting backup volume

If you want to check which backups are available on the PVC, here is a quick way to check:

```shell
kubectl run pvc-browser -it \
  --image=debian:12-slim \
  --restart=Never \
  --rm \
  --overrides='{
    "spec": {
      "containers": [{
        "name": "shell",
        "image": "debian:12-slim",
        "command": ["/bin/bash"],
        "stdin": true,
        "tty": true,
        "volumeMounts": [{
          "name": "backup-volume",
          "mountPath": "/data"
        }]
      }],
      "volumes": [{
        "name": "backup-volume",
        "persistentVolumeClaim": {
          "claimName": "backup"
        }
      }]
    }
  }'
```

This should spawn the new Pod with attached PVC, so you can browse:

```text
❯ kubectl run pvc-browser -it \
  --image=debian:12-slim \
  --restart=Never
[...]
If you don't see a command prompt, try pressing enter.

root@pvc-browser:/# ls /data/
0-backup-target.txt              backup.2026-03-27T16:00:02Z.sql  backup.2026-03-30T01:00:08Z.sql
backup.2026-03-25T08:00:03Z.sql  backup.2026-03-27T17:00:01Z.sql  backup.2026-03-30T02:00:10Z.sql
backup.2026-03-25T09:00:10Z.sql  backup.2026-03-27T18:00:05Z.sql  backup.2026-03-30T03:00:04Z.sql
backup.2026-03-25T10:00:04Z.sql  backup.2026-03-27T20:22:42Z.sql  backup.2026-03-30T04:00:07Z.sql
backup.2026-03-25T11:00:06Z.sql  backup.2026-03-27T20:22:58Z.sql  backup.2026-03-30T05:00:02Z.sql
backup.2026-03-25T12:00:10Z.sql  backup.2026-03-27T21:00:07Z.sql  backup.2026-03-30T06:00:03Z.sql
backup.2026-03-25T13:00:02Z.sql  backup.2026-03-27T22:00:20Z.sql  backup.2026-03-30T07:00:07Z.sql
backup.2026-03-25T14:00:06Z.sql  backup.2026-03-27T23:00:06Z.sql  backup.2026-03-30T08:00:09Z.sql
backup.2026-03-25T15:00:07Z.sql  backup.2026-03-28T00:00:07Z.sql  backup.2026-03-30T09:00:11Z.sql
backup.2026-03-27T14:00:09Z.sql  backup.2026-03-29T23:00:05Z.sql  lost+found
backup.2026-03-27T15:00:09Z.sql  backup.2026-03-30T00:00:03Z.sql
root@pvc-browser:/#
```

Don't leave that session running for too long. The backups may be blocked while this pod is running.
Usually you don't need the exact filename for restore, but it's good to know what is available out there.

## Restoring - nuclear option

In some cases, the restore may fail. For example, during recent incident, the existing database has been completely wiped.
When the OpenStack services restarted, naturally they assumed they are running on a fresh database so the migrations were executed.
As a result, the tables were already created but the other data was not there.
This also prevents the normal MariaDB restore process from working.

Here is how it looks like in the restore pod logs:

```text
{"level":"info","ts":1775026592.1292808,"msg":"writing target file","file":"/backup/0-backup-target.txt","file-content":"/backup/backup.2026-03-27T18:00:05Z.sql"}
💾 Restoring backup: /backup/backup.2026-03-27T18:00:05Z.sql
--------------
CREATE TABLE `attachment_specs` (
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `deleted` tinyint(1) DEFAULT NULL,
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `attachment_id` varchar(36) NOT NULL,
  `key` varchar(255) DEFAULT NULL,
  `value` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_attachment_specs_attachment_id` (`attachment_id`),
  CONSTRAINT `attachment_specs_ibfk_1` FOREIGN KEY (`attachment_id`) REFERENCES `volume_attachment` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_general_ci
--------------
ERROR 1005 (HY000) at line 56: Can't create table `cinder`.`attachment_specs` (errno: 150 "Foreign key constraint is incorrectly formed")
```

The solution is to delete the database and bootstrap new one from existing backup. High level steps are:

- Disable ArgoCD
- Make backup of the MariaDB cluster manifest and verify backups
- Delete storage
- Recreate the MariaDB cluster and users
- Restart OpenStack services

### Disable ArgoCD

This can be done by removing the relevant ClusterRoleBinding (make a local copy!) or pausing sync of all Applications (not possible in production environments). Example commands:

```shell
kubectl get clusterrolebinding argo-binding -o yaml > iad3-dev-clusterrolebinding-argo.yaml
kubectl delete clusterrolebinding argo-binding
```

### MariaDB resource backup

Obtain local copy of the `MariaDB` resource:

```shell
kubectl get mariadb mariadb -o yaml > mariadb-cluster-original.yaml
```

### Verify Backups

Double check that the backups exist. See [inspecting backups](#inspecting-backup-volume) section.

### Delete MariaDB resource

```shell
kubectl -n openstack delete mariadb mariadb
```

Verify that it was deleted with

```shell
kubectl -n openstack get mariadb
```

### Delete underlying storage

Delete database cluster PVCs:

```shell
kubectl delete pvc galera-mariadb-0 galera-mariadb-1 galera-mariadb-2 storage-mariadb-0 storage-mariadb-1 storage-mariadb-2
```

### Prepare recovery with bootstrap

```shell
cp mariadb-cluster-original.yaml mariadb-bootstrap-from-backup.yaml
vim mariadb-bootstrap-from-backup.yaml
```

Update the manifest by adding following snippet under `spec` section:

```yaml
bootstrapFrom:
  backupRef:
    name: backup
  targetRecoveryTime: 2026-03-27T18:00:00Z
```

Make sure to adjust the `targetRecoveryTime` to the desired recovery point.

Verify with:

```yaml
❯ cat mariadb-bootstrap-from-backup.yaml | yq .spec.bootstrapFrom
backupRef:
  name: backup
targetRecoveryTime: 2026-03-27T18:00:00Z
```

### Execute recovery

```shell
kubectl create -f mariadb-bootstrap-from-backup.yaml
```

Monitor progress with:

```shell
❯ kubectl  get mariadb
NAME      READY   STATUS      PRIMARY     UPDATES                    AGE
mariadb   True    Restoring   mariadb-1   ReplicasFirstPrimaryLast   17m
...
...
❯ kubectl  get mariadb
NAME      READY   STATUS      PRIMARY     UPDATES                    AGE
mariadb   True    Running     mariadb-1   ReplicasFirstPrimaryLast   47m
```

### Recreate Users

We have noticed that restore process is not always successful with restoring local users.
The solution for this is to simply delete the relevant `User` resources and
allow ArgoCD to recreate the, which forces the operator to recreate them in the
database:

```shell
kubectl get users --no-headers -o name | xargs kubectl delete
```

### Restart Services

#### Deployments

```shell

kubectl get deployments -o name |
  grep -Ev 'ovn|memcached|mariadb|eventsource|sensor' |
  xargs kubectl rollout restart

```

#### StatefulSets

```shell
kubectl get statefulset -o name |
  grep -Ev 'mariadb|ovs|rabbit|eventbus' |
  xargs kubectl rollout restart statefulset
```

### Restore ArgoCD access

```shell
kubectl create -f iad3-dev-clusterrolebinding-argo.yaml
```

## Galera Backup failures

Sometimes the mariadb-operator attempts to take a database backup but fails
with following error:

```text
💾 Exporting env
💾 Writing target file: /backup/0-backup-target.txt
💾 Taking backup: /backup/backup.2025-10-14T09:07:35Z.sql
-- Connecting to mariadb-primary.openstack.svc.cluster.local...
-- Starting transaction...
mariadb-dump: Got error: 1102: "Incorrect database name '#mysql50#.sst'" when selecting the database
```

This is generally caused by the leftover replication folder after pod crash
during a synchronization. If you go to a datadir (`/var/lib/mysql/` by
default), you won't be able to find the `#mysql50#.sst` folder though because
the folder name is just `.sst`. Verify if it's empty, remove it and backups
should start working again.

## Recovering from invalid root password

Recently, we have experienced a set of outages where the local root user account was lost following the replication between the nodes.
It seems to be very similar to what happens in
<https://github.com/mariadb-operator/mariadb-operator/issues/1448>, but we have
not been able to confirm the root cause yet. However, to recover we have tried
all of the suggested solutions:

- deleting the pods
- deleting the pods and their underlying PVCs
and none of them worked, one of the pods always eventually ended up with corrupted accounts.

Following several tries I have found out a semi-reliable way to recover from this. These are high-level steps:

1. Edit the mariadb cluster CRD by running `kubectl edit mariadb mariadb` and change the `suspend: false` to `suspend: true`. This will temporarily pause the operator.
2. Launch a debug pod that will give you access to the underlying PVC. Make sure that debug pod is scheduled on the same physical node as the one experiencing problems. This is the one I've used:

    ```yaml
    apiVersion: v1
    kind: Pod
    metadata:
      name: mariadb-pvc-debugger
    spec:
      volumes:
        - name: mariadb-data
          persistentVolumeClaim:
            claimName: storage-mariadb-2
      nodeName: infra3
      containers:
        - name: debugger
          image: docker-registry1.mariadb.com/library/mariadb:11.4.4
          command: ['/bin/sleep', '86400']
          args: []
          volumeMounts:
            - mountPath: "/var/lib/mysql/"
              name: mariadb-data
    ```

3. Scale down the `mariadb` statefulset to `0` replicas in order to release the lock.

    ```text
    kubectl scale statefulset mariadb --replicas 0
    ```

4. Obtain the root password:

    ```text
    kubectl -n openstack get secrets mariadb -o jsonpath='{.data.root-password}' | base64 -d
    ```

5. Exec into debug pod and start a local mariadb instance and reset the password

    ```text
    kubectl exec -it mariadb-pvc-debugger -- bash
    mysql@mariadb-pvc-debugger:/$
    mysql@mariadb-pvc-debugger:/$ mariadb-safe --skip-networking --skip-grant-tables &
    mysql@mariadb-pvc-debugger:/$
    mysql@mariadb-pvc-debugger:/$ mariadb -u root
    Welcome to the MariaDB monitor.  Commands end with ; or \g.
    Your MariaDB connection id is 2157
    Server version: 11.4.4-MariaDB-ubu2404 mariadb.org binary distribution

    Copyright (c) 2000, 2018, Oracle, MariaDB Corporation Ab and others.

    Type 'help;' or '\h' for help. Type '\c' to clear the current input statement.

    MariaDB [(none)]> FLUSH PRIVILEGES;
    Query OK, 0 rows affected (0.007 sec)
    MariaDB [(none)]>
    MariaDB [(none)]> CREATE USER IF NOT EXISTS 'root'@'::1' IDENTIFIED BY '<YOUR-PASSWORD>';
    Query OK, 0 rows affected (0.015 sec)

    MariaDB [(none)]> FLUSH PRIVILEGES;
    Query OK, 0 rows affected (0.007 sec)

    MariaDB [(none)]> GRANT ALL PRIVILEGES ON *.* TO 'root'@'::1' WITH GRANT OPTION;
    MariaDB [(none)]> CREATE USER IF NOT EXISTS 'root'@'localhost' IDENTIFIED BY '<YOUR-PASSWORD>';
    Query OK, 0 rows affected (0.015 sec)

    MariaDB [(none)]> FLUSH PRIVILEGES;
    Query OK, 0 rows affected (0.007 sec)

    MariaDB [(none)]> GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' WITH GRANT OPTION;
    ```

6. When this is done, close the MariaDB session and delete the pod.
7. Scale the StatefulSet back up to it's original number of replicas

    ```text
    kubectl scale statefulset mariadb --replicas 3
    ```

8. Resume the MariaDB operator by changing the `suspend: true` back to `suspend: false`

References:

- <https://github.com/mariadb-operator/mariadb-operator/blob/main/docs/galera.md#galera-cluster-recovery>
