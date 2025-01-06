# Getting Started

You will need to have available a number of local utilities,
a clone of this repo and another Git repo which will be referred to
as the deploy repo. You will also need at least once Kubernetes
cluster available to you, while multiple clusters are the advisable
approach for any production or deployment at scale as the [Introduction](./index.md)
mentions.

Embracing [GitOps][gitops] and declarative configuration, we will need to have
some items available before we begin.

1. A Git repo that you'll be able to commit to and that you'll be able to provide
read-only credentials to the tooling to fetch data from. Something like
[GitHub Deploy Keys][gh-deploy-keys] will work.
2. A DNS zone under which you can create multiple DNS entries. You can use a service
like [sslip.io](https://sslip.io) for test purposes.
3. The ability to get SSL certificates for these domains via cert-manager.

[gitops]: <https://about.gitlab.com/topics/gitops/>
[gh-deploy-keys]: <https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys#set-up-deploy-keys>
