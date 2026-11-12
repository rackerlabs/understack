# OpenStack Ironic

## Deploy Ironic

NOTE: The PXE service currently has the host network devices mapped into
the container. You'll have to edit the [values.yaml](./values.tpl.yaml)
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
# create secrets yaml file if you're not already storing or providing it differently
./scripts/gen-os-secrets.sh secret-openstack.yaml
```

### Database and RabbitMQ

```bash
kubectl -n openstack apply -k components/ironic/
```

### OpenStack Helm

Firstly you must have the OpenStack Helm repo available, if you've done this
previously you do not need to do it again.

```bash
helm repo add osh https://tarballs.opendev.org/openstack/openstack-helm/
```

Now customize `components/ironic/values.tpl.yaml` and then install or upgrade Ironic.

```bash
helm --namespace openstack \
    install \
    ironic osh/ironic \
    -f components/images-openstack.yaml \
    -f components/ironic/values.yaml \
    -f components/ironic/values.tpl.yaml \
    -f secret-openstack.yaml
```

At this point Ironic will go through some initialization and start up.

## PCI device traits

The `pci-device-trait` inspection hook counts PCI devices that match aliases
configured in the `[ironic_understack]` section of `ironic.conf`. Each alias is
a JSON object with `vendor_id`, `product_id`, and `name` fields. In the
OpenStack-Helm values this is configured as:

```yaml
conf:
  ironic:
    ironic_understack:
      pci_device_alias:
        - '{"vendor_id": "1002", "product_id": "75a8", "name": "gpu_amd_mi350p"}'
```

The option uses the same JSON `MultiStrOpt` format as Ironic's upstream
`pci_device_alias` option, but remains in the `[ironic_understack]` section.
The hook normalizes the alias name and adds a custom trait containing the
number of matching devices. For example, a node with two matching devices from
the configuration above receives the `CUSTOM_PCI_2_GPU_AMD_MI350P` trait.

On subsequent inspections, the hook replaces traits in the `CUSTOM_PCI_`
namespace with the current counts while preserving all other node traits.

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
