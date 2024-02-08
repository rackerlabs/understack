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
cd components/10-keystone
```

## Deploy Keystone

Since we cannot refer to the secrets by name, we must look them up live from the cluster
so that we can injected them into the templated configs. Upstream should really allow
secrets to be passed by reference. As a result of this we cannot use GitOps to generate
these charts and have them applied to the cluster.

Secrets Reference:

- openstack-default-user is created by the messaging-topology-operator which is
  executed by the rabbitmq-queues component. The name stems from the RabbitMQ
  cluster from the rabbitmq-cluster component. `${CLUSTER_NAME}-default-user`

```bash
helm --namespace openstack template \
    keystone \
    $(git rev-parse --show-toplevel)/openstack-helm/keystone/ \
    -f aio-values.yaml \
    --set endpoints.identity.auth.admin.password="$(kubectl --namespace openstack get secret keystone-admin -o jsonpath='{.data.password}' | base64 -d)" \
    --set endpoints.oslo_db.auth.admin.password="$(kubectl --namespace openstack get secret mariadb -o jsonpath='{.data.root-password}' | base64 -d)" \
    --set endpoints.oslo_db.auth.keystone.password="$(kubectl --namespace openstack get secret keystone-db-password -o jsonpath='{.data.password}' | base64 -d)" \
    --set endpoints.oslo_messaging.auth.admin.password="$(kubectl --namespace openstack get secret openstack-default-user -o jsonpath='{.data.password}' | base64 -d)" \
    --set endpoints.oslo_messaging.auth.keystone.password="$(kubectl --namespace openstack get secret keystone-rabbitmq-password -o jsonpath='{.data.password}' | base64 -d)" \
    --post-renderer $(git rev-parse --show-toplevel)/scripts/openstack-helm-sealed-secrets.sh \
    | kubectl -n openstack apply -f -
```

At this point Keystone will go through some initialization and start uo.

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
