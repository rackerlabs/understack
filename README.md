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
- `cmctl`

Alternatively, if you don't have those dependencies you can use the dedicated
development environment including those tools by launching `nix-shell` in the
project directory. If you don't have `nix-shell` on your machine, it can be
[downloaded here](https://nixos.org/download.html).

### Bootstrapping and Operators

There's a handful of base required components to get a cluster ready to accept
traffic and utilize ArgoCD to deploy the rest of the stack. We'll call that
"bootstrap". Below is the easy one liner but you can look at
[./bootstrap/README.md](./bootstrap/README.md) for detailed info.

```bash
kubectl kustomize --enable-helm bootstrap | kubectl apply --server-side -f -
```

If you get following error:

```
error: resource mapping not found for name: "selfsigned-cluster-issuer"
namespace: "kube-system" from "STDIN": no matches for kind "ClusterIssuer" in
version "cert-manager.io/v1"
```

then you may need to rerun the same command as the CRDs are not [always fully
established](https://github.com/kubernetes/kubectl/issues/1117)
before when they are needed.

At this point ArgoCD can start doing the heavy lifting.

```bash
kubectl -n argocd apply -k apps/operators/
```

### Secrets

To make it possible to utilize GitOps, we need to have our secrets pre-created
and not randomly generated. A better solution for secrets will ultimately be
needed but for now we can generate them easily for a dev environment and
deploy them. Visit [/components/01-secrets/README.md](./components/01-secrets/README.md)
for specific steps.  Otherwise just follow the steps below.

```bash
# generate secrets
./scripts/easy-secrets-gen.sh
# make the namespaces where the secrets will live
kubectl apply -k components/00-namespaces/
# load the secrets
kubectl apply -k components/01-secrets/
```

### Deploy the UnderStack components

```bash
kubectl -n argocd apply -k apps/components/
```

ArgoCD should successfully get Nautobot deployed. Now come the OpenStack
components which aren't working with GitOps methods at this time.

[Install Keystone](./components/10-keystone/README.md)
