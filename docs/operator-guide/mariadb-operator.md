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
