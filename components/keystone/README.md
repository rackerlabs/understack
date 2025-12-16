# OpenStack Keystone

## Label the node(s)

In order to deploy Openstack control plane, at least one of the Kubernetes
nodes has to be labeled with `openstack-control-plane=enabled` label. If you
don't have a node that meets this condition yet, use command similar to this:

```bash
❯ kubectl label node $(kubectl get nodes -o 'jsonpath={.items[*].metadata.name}') openstack-control-plane=enabled
```

## Deploy Keystone

Since we cannot refer to the secrets by name, we must look them up live from the cluster
so that we can injected them into the templated configs. Upstream should really allow
secrets to be passed by reference. As a result of this we cannot use GitOps to generate
these charts and have them applied to the cluster.

### Secrets Reference

- keystone-admin is the admin password for creating other users, services and endpoints.
  It is used by the initialization / bootstrap jobs.
- keystone-db-password is the DB password for the keystone DB user.
- keystone-rabbitmq-password is the RabbitMQ password for the keystone user.

```bash
# create secrets yaml file if you're not already storing or providing it differently
./scripts/gen-os-secrets.sh secret-openstack.yaml
```

### Database and RabbitMQ

```bash
kubectl -n openstack apply -k components/keystone/
```

### OpenStack Helm

Firstly you must have the OpenStack Helm repo available, if you've done this
previously you do not need to do it again.

```bash
 helm repo add osh https://tarballs.opendev.org/openstack/openstack-helm/
 ```

Now install or upgrade Keystone.

```bash
helm --namespace openstack \
  install \
  keystone osh/keystone \
  -f components/images-openstack.yaml \
  -f components/keystone/values.yaml \
  -f secret-openstack.yaml
```

At this point Keystone will go through some initialization and start up.

## Validating Keystone

You can run an OpenStack client in the cluster to validate it is running correctly.

```bash
# start up a pod with the client
kubectl -n openstack apply -f https://raw.githubusercontent.com/rackerlabs/genestack/main/manifests/utils/utils-openstack-client-admin.yaml
```

Show the catalog list

```bash
kubectl exec -it openstack-admin-client -n openstack -- openstack catalog list
```

Show the service list

```bash
kubectl exec -it openstack-admin-client -n openstack -- openstack service list
```
