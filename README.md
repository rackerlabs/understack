# UnderStack

An opinionated installation of OpenStack and related services to
be able to provision bare metal hardware to be consumable by
[genestack](https://github.com/rackerlabs/genestack) for the
full OpenStack suite.

The requirements are a Kubernetes cluster, which
this repo will contain information about building different
clusters and then a pile of bare metal systems that can
be ingested into the stack to be available to be consumed
via Openstack Ironic.

## Basic Deploy

You will need a k8s cluster with PV provider (host path provisioner works).

### Prereqs

You must have the following installed:

- `yq` <https://github.com/mikefarah/yq>
- `kustomize` (5.x versions)
- `helm` (3.8 or newer)
- `kubeseal`

### Bootstrapping and Operators

There's a handful of base required components to get a cluster ready to accept traffic
and utilize ArgoCD to deploy the rest of the stack. We'll call that "bootstrap". Below
is the easy one liner but you can look at [./bootstrap/README.md](./bootstrap/README.md)
for detailed info.

```bash
kubectl kustomize --enable-helm bootstrap | kubectl apply --server-side -f -
```

At this point ArgoCD can start doing the heavy lifting.

```bash
kubectl -n argocd apply -k apps/operators/
```

### Secrets

Visit [./components/01-secrets](./components/01-secrets) and follow the steps there to
generate the secrets you'll need. And then load them.

```bash
# make the namespaces where the secrets will live
kubectl apply -k components/00-namespaces/
# load the secrets
kubectl apply -k components/01-secrets/
```

### Deploy the UnderStack components

```bash
kubectl -n argocd apply -k apps/components/
```

ArgoCD should successfully get everything deployed.
