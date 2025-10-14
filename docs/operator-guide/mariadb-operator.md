# MariaDB Operator

Useful commands for working with the MariaDB operator.

Docs: <https://mariadb-operator.github.io/mariadb-operator/latest/>

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
    kubectl scale statefulset mariadb --replicas 0`
    ```

4. Obtain the root password:

    ```text
    kubectl -n openstack get secrets mariadb -o jsonpath='{.data.root-password}' | base64 -d
    ```

5. Exec into debug pod and start a local mariadb instance and reset the password

    ```text
    kubect exec -it mariadb-pvc-debugger -- bash
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
