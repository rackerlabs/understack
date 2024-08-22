# Postgres Operator Cheat Sheet

Useful commands for working with the PostgreSQL operator.

## CloudNative PostgresQL Operator

Docs: <https://cloudnative-pg.io/>

Repo: <https://github.com/cloudnative-pg/cloudnative-pg>

## List postgres database clusters

```bash
kubectl -n nautobot get cluster
```

You should see something like this:

```output
  kubectl get cluster
NAME               AGE     INSTANCES   READY   STATUS                     PRIMARY
nautobot-cluster   6m11s   3           3       Cluster in healthy state   nautobot-cluster-1
```

## Describe the Nautobot postgres database cluster

```bash
kubectl -n nautobot describe cluster nautobot-cluster
```

## Connect to the Nautobot database with psql command line

```bash
# This is the name of the secret with the nautobot postgres credentials
PG_CLUSTER_SECRET=nautobot-cluster-app

# psql command line which loads the credentials from the secret
PGPASSWORD=$(kubectl get secret -n nautobot "${PG_CLUSTER_SECRET}" -o go-template='{{.data.password | base64decode}}') PGUSER=$(kubectl get secret -n nautobot "${PG_CLUSTER_SECRET}" -o go-template='{{.data.user | base64decode}}') PGDATABASE=$(kubectl get secret -n nautobot "${PG_CLUSTER_SECRET}" -o go-template='{{.data.dbname | base64decode}}') psql -h localhost
```

## Create a local pg_dump backup of the Nautobot database

First we need to create a kubernetes port forward for our local machine
to be able to connect to the primary postgres pod in kubernetes.

```bash
# Get the primary postgres server pod
PG_CLUSTER_PRIMARY_POD=$(kubectl get pod -n nautobot -o name -l cnpg.io/cluster=nautobot-cluster,cnpg.io/instanceRole=primary)

# Create a port forward for local port 5432 to reach the postgres server pod
kubectl -n nautobot port-forward "${PG_CLUSTER_PRIMARY_POD}" 5432:5432
```

Once the port forward has been created, we can perform a `pg_dump` of the postgres database:

```bash
PG_CLUSTER_SECRET=nautobot-cluster-app
PGPASSWORD=$(kubectl get secret -n nautobot "${PG_CLUSTER_SECRET}" -o go-template='{{.data.password | base64decode}}') PGUSER=$(kubectl get secret -n nautobot "${PG_CLUSTER_SECRET}" -o go-template='{{.data.user | base64decode}}') PGDATABASE=$(kubectl get secret -n nautobot "${PG_CLUSTER_SECRET}" -o go-template='{{.data.dbname | base64decode}}') pg_dump -h localhost -f nautobot.postgres.sql
```
