# Getting Started

To get started, ensure you have the following prerequisites:

* A clone of this repository.
* Another [Git repository,](#deploy-repository) referred to as the
  [Deploy Repository](#deploy-repository).
* Access to at least one Kubernetes cluster.

For simplicity, you can use an All-In-One deployment. However, for
production or large-scale deployments, it is recommended to use multiple
clusters, as outlined in the [System Division](./welcome.md#system-division).

This approach embraces [GitOps][gitops] and declarative configuration.

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
5. The definitions of the hardware flavors that this cluster, which later you will see maps to a site.
6. This contains data which the cluster labeled as `iad3-staging` will consume.
7. The definitions of the hardware flavors that this cluster, which later you will see maps to a site. Notice it is different than staging.
8. The cluster labeled as `global-prod` will have resources consumed here.

### Deploy repository permissions

To get started, you'll need a Deploy Repository that you can commit to. This means you should have write access to this repository.

For the deployment tool, [ArgoCD][argocd], you'll need to set up read-only credentials. This allows ArgoCD to fetch the necessary data without making any changes to your repository. One way to achieve this is by using [GitHub Deploy Keys][gh-deploy-keys] or similar solutions.

[GitHub Deploy Keys][gh-deploy-keys] will work.

## UnderStack Repository

The UnderStack repository is used as a base for services installed, their
versions, common configs and containers. It will be referenced by the [ArgoCD][argocd]
Application which in turn will
reference ApplicationSets and the services, their versions and their source repositories.

[argocd]: <https://argo-cd.readthedocs.io/en/stable/>
[gitops]: <https://about.gitlab.com/topics/gitops/>
[gh-deploy-keys]: <https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys#set-up-deploy-keys>

## DNS and SSL

You will need a DNS zone under which you can make multiple DNS records and
utilize [cert-manager](https://cert-manager.io) to get SSL certificates for HTTPS access.
You may use something like [sslip.io](https://sslip.io) for test purposes.
