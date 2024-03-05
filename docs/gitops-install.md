# GitOps based Install

This guide is not meant to be a definitive guide to [GitOps][gitops] and
how it can be used with UnderStack or even a best practices example
but instead focused on an example development oriented installation.
It will make a few assumptions and some opinionated choices that may
not align with a production best practices installation.
Most notable assumptions are:

- [GitOps][gitops] tooling runs on the same cluster as the deploy
- AIO (All-in-One) configuration
- Your cluster is a blank slate and can be entirely consumed

You will have the source to your deployment and all the pre-deployment
work will occur on your local machine and not on any of the target
machines.

## Getting the source

You must fetch the source to this repo and since we will be using
[GitOps][gitops], you must also have a deployment repo. These
operations can all happen locally on your development machine.

```bash
git clone https://github.com/rackerlabs/understack
# then either
git init uc-deploy
# or
git clone https://path/to/my/uc-deploy
```

## Pre-deployment

Embracing GitOps and declarative configuration, we will define three
distinct pieces of information for your deployment.

- Infrastructure: Where the software will live (TODO: this defines the cluster)
- Secrets: What are all the credentials, passwords, etc needed by the software
- Cluster: The actual software that will be deployed

To properly scope this you'll need an environment name. For the
purposes of this document we'll call it `my-k3s`.

### Environment Variables

To avoid defining many environment variables we'll simplify by creating an
`.env` file for our deployment. In this case we'll call it `my-k3s.env` and
place it where we've cloned understack.

```bash title="/path/to/understack/my-k3s.env"
UC_REPO="/path/to/understack"
UC_DEPLOY="/path/to/uc-deploy"
DEPLOY_NAME="my-k3s"
```

### Remaining pre-deployment config

ArgoCD will need to know where it can access your deployment config
repo. This can be over SSH with a key or over HTTPS. Add to your
`my-k3s.env` the following:

```bash title="/path/to/understack/my-k3s.env"
UC_DEPLOY_GIT_URL="git@github.com:my-org/uc-deploy.git"
UC_DEPLOY_SSH_FILE="/path/to/ssh.private"
```

All services will utilize unique DNS names. The facilitate this, UnderStack
will take a domain and add sub-domains for them. Add to your `my-k3s.env`
the following:

```bash title="/path/to/understack/my-k3s.env"
DNS_ZONE="some.domain.corp"
```

### Populating the infrastructure

TODO: some examples and documentation on how to build out a cluster

### Generating secrets

Secrets in their very nature are sensitive pieces of data. The ultimate
storage and injection of these in a production environment needs to be
carefully considered. For the purposes of this document no specific
choice has been made but tools like Vault, Sealed Secrets, SOPS, etc
should be considered. This will only generate the necessary secrets
using random data to sucessfully continue the installation.

TODO: probably give at least one secure example

```bash
./scripts/gitops-secrets-gen.sh ./my-k3s.env
cd /path/to/uc-deploy
git add secrets/my-k3s
git commit -m "my-k3s: secrets generation"
```

### Defining the app deployment

In this section we will use the [App of Apps][app-of-apps] pattern to define
the deployment of all the components of UnderStack.

```bash
./scripts/gitops-deploy.sh ./my-k3s.env
cd /path/to/uc-deploy
git add clusters/my-k3s
git commit -m "my-k3s: initial cluster config"
```

## Final modifications of your deployment

This is point you can make changes to the [ArgoCD][argocd] configs before
you do the deployment.

## Doing the Deployment

At this point we will use our configs to make the actual deployment.
Make sure everything you've committed to your deployment repo is pushed
to your git server so that ArgoCD can access it.

If you do not have ArgoCD deployed then you can use the following:

```bash
kubectl kustomize --enable-helm \
    https://github.com/rackerlabs/understack//bootstrap/argocd/ \
    | kubectl apply -f -
```

Then run the following:

```bash
kubectl apply -f "/path/to/uc-deploy/clusters/my-k3s/app-of-apps.yaml"
```

At this point ArgoCD will work to deploy Understack.

[gitops]: <https://about.gitlab.com/topics/gitops/>
[app-of-apps]: <https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/>
[argocd]: <https://argo-cd.readthedocs.io/en/stable/>
