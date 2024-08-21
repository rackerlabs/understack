# Postgres Operator Cheat Sheet

Useful commands for working with the PostgreSQL operator.

## List databases

```bash
kubectl -n nautobot get postgrescluster
```

## Describe the Nautobot postgres database

```bash
kubectl describe postgrescluster nautobot
```

## Connect to the Nautobot database with psql command line

```bash
# This is the name of the secret with the nautobot postgres credentials
PG_CLUSTER_USER_SECRET_NAME=nautobot-pguser-nautobot

# psql command line which loads the credentials from the secret
PGPASSWORD=$(kubectl get secret -n nautobot "${PG_CLUSTER_USER_SECRET_NAME}" -o go-template='{{.data.password | base64decode}}') PGUSER=$(kubectl get secret -n nautobot "${PG_CLUSTER_USER_SECRET_NAME}" -o go-template='{{.data.user | base64decode}}') PGDATABASE=$(kubectl get secret -n nautobot "${PG_CLUSTER_USER_SECRET_NAME}" -o go-template='{{.data.dbname | base64decode}}') psql -h localhost
```

## Create a local pg_dump backup of the Nautobot database

First we need to create a kubernetes port forward for our local machine
to be able to connect to the primary postgres pod in kubernetes.

```bash
# Get the primary postgres server pod
PG_CLUSTER_PRIMARY_POD=$(kubectl get pod -n nautobot -o name \
  -l postgres-operator.crunchydata.com/cluster=nautobot,postgres-operator.crunchydata.com/role=master)

# Create a port forward for local port 5432 to reach the postgres server pod
kubectl -n nautobot port-forward "${PG_CLUSTER_PRIMARY_POD}" 5432:5432
```

Once the port forward has been created, we can perform a `pg_dump` of the postgres database:

```bash
PG_CLUSTER_USER_SECRET_NAME=nautobot-pguser-nautobot
PGPASSWORD=$(kubectl get secret -n nautobot "${PG_CLUSTER_USER_SECRET_NAME}" -o go-template='{{.data.password | base64decode}}') PGUSER=$(kubectl get secret -n nautobot "${PG_CLUSTER_USER_SECRET_NAME}" -o go-template='{{.data.user | base64decode}}') PGDATABASE=$(kubectl get secret -n nautobot "${PG_CLUSTER_USER_SECRET_NAME}" -o go-template='{{.data.dbname | base64decode}}') pg_dump -h localhost -f nautobot.postgres.sql
```
