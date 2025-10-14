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
