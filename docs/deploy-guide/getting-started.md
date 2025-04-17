# Getting Started

You will need to have available a number of local utilities,
a clone of this repo and another Git repo which will be referred to
as the deploy repo. You will also need at least one Kubernetes
cluster available to you, which can be an All-In-One deployment,
while multiple clusters are the advisable approach, as described
in the [System Division](./welcome.md#system-division),
for any production or deployment at scale.

Embracing [GitOps][gitops] and declarative configuration, we will need to have
some items available before we begin.

1. A Git repo, which will be your [Deploy Repository](#deploy-repository) that you'll
be able to commit to and that you'll be able to provide
read-only credentials to the tooling to fetch data from. Something like
[GitHub Deploy Keys][gh-deploy-keys] will work.
2. A DNS zone under which you can create multiple DNS entries. You can use a service
like [sslip.io](https://sslip.io) for test purposes.
3. The ability to get SSL certificates for these domains via cert-manager.

## Deploy Repository

The deployment repository will contain configuration related to your deployment.
Some of these items may be Kubernetes manifests or custom resources which will
be consumed by different tools. It is recommended that one Deploy Repository
is used per Management tier, see [Introduction](./welcome.md) for information
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
3. Any Kubernetes manifests per application/component will be here for `management`.
4. This contains data which the cluster labeled as `iad3-prod` will consume.
5. The definitions of the hardware flavors that this cluster, which later you will see maps to a region will use.
6. This contains data which the cluster labeled as `iad3-staging` will consume.
7. The definitions of the hardware flavors that this cluster, which later you will see maps to a region will use. Notice it is different than staging.
8. The cluster labeled as `global-prod` will have resources consumed here.

## UnderStack Repository

The UnderStack repository is used as a base for services installed, their
versions, common configs and containers. It will be referenced by the [ArgoCD][argocd]
Application which in turn will
reference ApplicationSets and the services, their versions and their source repositories.

[argocd]: <https://argo-cd.readthedocs.io/en/stable/>
[gitops]: <https://about.gitlab.com/topics/gitops/>
[gh-deploy-keys]: <https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys#set-up-deploy-keys>
