# UnderStack

An opinionated installation of OpenStack and related services to
be able to provision bare metal hardware to be consumable by
[genestack](https://github.com/rackerlabs/genestack) for the
full OpenStack suite.

The requirements are a Kubernetes cluster, which
this repo will contain information about building different
clusters and then a pile of bare metal systems that can
be ingested into the stack to be available to be consumed
via OpenStack Ironic.

## Basic Deploy

You will need a k8s cluster with PV provider (host path provisioner works).

### Prereqs

You must have the following installed:

- `yq` <https://github.com/mikefarah/yq>
- `kustomize` (5.x versions)
- `helm` (3.8 or newer)
- `kubeseal`

Alternatively, if you don't have those dependencies you can use the dedicated
development environment including those tools by launching `nix-shell` in the
project directory. If you don't have `nix-shell` on your machine, it can be
[downloaded here](https://nixos.org/download.html).

### Install

Follow the [GitOps Install
Guide](https://rackerlabs.github.io/understack/deploy-guide/gitops-install/)
which walks through creating a configuration and bootstrapping UnderStack.
