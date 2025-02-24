# OpenStack Helm

If you need to troubleshoot how OpenStack Helm is deploying some components
you can utilize `helm` against your cluster to see what would differ or
change from what's been deployed. You will need the following:

- access to your k8s cluster
- the `helm` binary installed
- in the same working directory the following repos cloned:
    - openstack-helm
    - openstack-helm-infra
    - understack
    - your-deploy

You can generate what ArgoCD would deploy for `ironic` by running:

```bash
# first we need to build the dependencies
helm dependency build openstack-helm/ironic
```

```bash
helm template \
    ironic \  # what we are deploying
    openstack-helm/ironic \  # the path the chart's source is in
    --namespace openstack \
    -f understack/components/openstack-2024.2-jammy.yaml \  # the version we are deploying
    -f understack/components/ironic/values.yaml \  # common configs
    -f your-deploy/$YOUR_ENV/manifests/secret-openstack.yaml \  # credentials
    -f your-deploy/$YOUR_ENV/helm-configs/ironic.yaml  # your specific overrides
```

For another component change all instances of `ironic` to the one you want to target.

You can also diff it against the cluster with:

```bash
helm template \
    ironic \  # what we are deploying
    openstack-helm/ironic \  # the path the chart's source is in
    --namespace openstack \
    -f understack/components/openstack-2024.2-jammy.yaml \  # the version we are deploying
    -f understack/components/ironic/values.yaml \  # common configs
    -f your-deploy/$YOUR_ENV/manifests/secret-openstack.yaml \  # credentials
    -f your-deploy/$YOUR_ENV/helm-configs/ironic.yaml \  # your specific overrides
    | kubectl -n openstack diff -f -
```
