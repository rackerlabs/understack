# bootstrap

These are the bare minimum steps required to bootstrap your cluster up to ArgoCD which will then deploy the applications.

Each component is installed with a manifest referenced in a child directory.  The components at this time are:

- [cert-manager](https://cert-manager.io/docs/)
- [ArgoCD](https://argo-cd.readthedocs.io/en/stable/)
