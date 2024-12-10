# Deploy Repository

The deployment repository will contain configuration related to your deployment.
Some of these items may be Kubernetes manifests or custom resources which will
be consumed by different tools. It is recommended that one Deploy Repository
is used per Management tier, see [Introduction](./index.md) for information
on what this is.

The layout of this repo will be something like:

```shell
.
├── management # (1)
│   ├── helm-configs # (2)
│   └── manifests # (3)
├── iad3-prod # (4)
│   ├── flavors -> ../flavors/prod # (5)
│   ├── helm-configs
│   └── manifests
├── iad3-staging # (6)
│   ├── flavors -> ../flavors/nonprod # (7)
│   ├── helm-configs
│   └── manifests
├── global-prod # (8)
│   ├── helm-configs
│   └── manifests
└── flavors
    ├── nonprod
    └── prod
```

1. This contains data which the cluster labeled as `management` will consume.
2. helm `values.yaml` files per application/component will be here for `management`.
3. Any kubernetes manifests per application/component will be here for `management`.
4. This contains data which the cluster labeled as `iad3-prod` will consume.
5. The definitions of the hardware flavors that this cluster, which later you will see maps to a region will use.
6. This contains data which the cluster labeled as `iad3-staging` will consume.
7. The definitions of the hardware flavors that this cluster, which later you will see maps to a region will use. Notice it is different than staging.
8. The cluster labeled as `global-prod` will have resources consumed here.
