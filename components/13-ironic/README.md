# OpenStack Ironic

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
./scripts/openstack-helm-depend-sync.sh ironic
```

## Deploy Ironic

NOTE: The PXE service currently has the host network devices mapped into
the container. You'll have to edit the [aio-values.yaml](./aio-values.yaml)
file in the `network.pxe.device` field to the correct value for your
server to have this start up successfully.

Since we cannot refer to the secrets by name, we must look them up live from the cluster
so that we can inject them into the templated configs. Upstream should really allow
secrets to be passed by reference. As a result of this we cannot use GitOps to generate
these charts and have them applied to the cluster.

Secrets Reference:

- keystone-admin is the admin password for creating other users, services and endpoints.
  It is used by the initialization / bootstrap jobs.
- ironic-db-password is the DB password for the ironic DB user.
- ironic-rabbitmq-password is the RabbitMQ password for the ironic user.
- ironic-keystone-password is the Keystone service account for the Ironic service, this
  is created by the ks-user job using the keystone-admin credential.

```bash
helm --namespace openstack template \
    ironic \
    ./openstack-helm/ironic/ \
    -f components/openstack-2023.1-jammy.yaml \
    -f components/13-ironic/aio-values.yaml \
    --set endpoints.identity.auth.admin.password="$(kubectl --namespace openstack get secret keystone-admin -o jsonpath='{.data.password}' | base64 -d)" \
    --set endpoints.oslo_db.auth.ironic.password="$(kubectl --namespace openstack get secret ironic-db-password -o jsonpath='{.data.password}' | base64 -d)" \
    --set endpoints.oslo_messaging.auth.ironic.password="$(kubectl --namespace openstack get secret ironic-rabbitmq-password -o jsonpath='{.data.password}' | base64 -d)" \
    --set endpoints.identity.auth.ironic.password="$(kubectl --namespace openstack get secret ironic-keystone-password -o jsonpath='{.data.password}' | base64 -d)" \
    --post-renderer $(git rev-parse --show-toplevel)/scripts/openstack-helm-sealed-secrets.sh \
    | kubectl -n openstack apply -f -
```

At this point Ironic will go through some initialization and start up.

## Validating Ironic

You can run an OpenStack client in the cluster to validate it is running correctly.

```bash
# start up a pod with the client
kubectl -n openstack apply -f https://raw.githubusercontent.com/rackerlabs/genestack/main/manifests/utils/utils-openstack-client-admin.yaml
```

Show the driver list

```bash
kubectl exec -it openstack-admin-client -n openstack -- openstack baremetal driver list
```

Show the conductor list

```bash
kubectl exec -it openstack-admin-client -n openstack -- openstack baremetal conductor list
```
