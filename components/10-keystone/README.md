# OpenStack Keystone

So unfortunately OpenStack Helm doesn't publish helm charts that can be consumed like
regular helm charts. You must instead clone two of their git repos side by side and
build the dependencies manually. They additionally don't split out secrets but instead
template them into giant config files or even executable scripts that then get stored
as secrets, a clear violation of <https://12factor.net>. As a result we cannot store
a declarative config of Keystone and allow users to supply their own secrets.

Due to the above issues, for now we'll skip the ArgoCD ability for this deployment.

## Get OpenStack Helm Ready

You may have done this for another OpenStack component and can share the same
git clones. This assumes you're doing this from the top level of this repo.

```bash
# clone the two repos because they reference the infra one as a relative path
# so you can't use real helm commands
git clone https://github.com/openstack/openstack-helm
git clone https://github.com/openstack/openstack-helm-infra
# update the dependencies cause we can't use real helm references
./scripts/openstack-helm-depend-sync.sh keystone
```

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

Secrets Reference:

- keystone-admin is the admin password for creating other users, services and endpoints.
  It is used by the initialization / bootstrap jobs.
- keystone-db-password is the DB password for the keystone DB user.
- keystone-rabbitmq-password is the RabbitMQ password for the keystone user.

```bash
# create secrets yaml file if you're not already storing or providing it differently
./scripts/gen-os-secrets.sh secret-openstack.yaml

helm --namespace openstack template \
    keystone \
    ./openstack-helm/keystone/ \
    -f components/openstack-2023.1-jammy.yaml \
    -f components/10-keystone/aio-values.yaml \
    -f secret-openstack.yaml \
    | kubectl -n openstack apply -f -
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
