# Management Cluster

The deployment of all the services into your Kubernetes cluster is handled
by [ArgoCD][argocd]. The [System Division](./welcome.md#system-division)
defines the location where [ArgoCD][argocd] runs as the __Management__ role.
While it is possible to run ArgoCD from the same cluster that your services
will run in, it is not advisable outside of a development setup. The
approach that UnderStack uses to deploy it's services with ArgoCD is the
[App of Apps pattern][argocd-app-of-apps].

## Deploying ArgoCD to your Management Cluster

If you already have [ArgoCD][argocd] deployed and available to be used then you
can skip this section.

The following command will do an initial deployment of ArgoCD that can
then be customized further.

```bash title="installing ArgoCD"
kubectl kustomize --enable-helm https://github.com/rackerlabs/understack/bootstrap/argocd/ | kubectl apply -f -
```

## Configuring your Global and/or Site Cluster in ArgoCD

For [ArgoCD][argocd] to be able to deploy to your cluster, you must define your cluster in
ArgoCD. You can do this one of two ways, via the `argocd` CLI tool or via the
[Declarative Setup][argocd-decl-setup]. We are embracing GitOps so the declarative
is what we'll use.

### Creating a Cluster Config

```bash title="declaring a cluster config"
DEPLOY_NAME=my-site # this should match one of your top-level directories in your deploy repo
DNS_ZONE="zone.where.all.dns.entries.will.live" # all services will have DNS entries under here

# assuming you are in the top-level of your deploy repo checkout
mkdir -p management/manifests/argocd/

cat << EOF > management/manifests/argocd/${DEPLOY_NAME}-cluster.yaml
apiVersion: v1
kind: Secret
metadata:
  name: ${DEPLOY_NAME}-cluster
  namespace: argocd
  annotations:
    dns_zone: "${DNS_ZONE}"
    understack.rackspace.com/env: prod
    understack.rackspace.com/role: site
  labels:
    argocd.argoproj.io/secret-type: cluster
type: Opaque
stringData:
  name: "${DEPLOY_NAME}"
  server: https://my-site-cluster:6443
  config: |
    # see link below for details

EOF
```

This file is not complete yet because you must configure the access to the
cluster by ArgoCD, please see [cluster config][argocd-decl-setup] for details
on how to complete this.

There are additional annotations supported by UnderStack as well for
different configurations.

`understack.rackspace.com/env`
: Possible values are `prod` and `dev`. If the value is set to `dev` then
  various settings can be overridden so allow an easier development experience.

`understack.rackspace.com/role`
: Possible values are `site`, `global`, and `aio`. Which defines what
  services should be deployed to this cluster based on its role. The `aio`
  role stands for "All In One" and combines both `site` and `global`.

`dns_zone`
: The DNS zone under which all services in this cluster will have their DNS
  records created.

`uc_repo_git_url`
: URL to the UnderStack git repo to use. Can only be set for `dev` env
  clusters.

`uc_repo_ref`
: Git reference to use of the UnderStack repo. Can only be set for `dev` env
  clusters.

`uc_deploy_git_url`
: URL to the deploy git repo to use. Can only be set for `dev` env
  clusters.

`uc_deploy_ref`
: Git reference to use of the deploy repo. Can only be set for `dev` env
  clusters.

### Deploying your Cluster Config

Once you have the Kubernetes secret which defines your cluster config ready
you must commit it to your deploy repo and then deploy it to your ArgoCD.

In your deploy repo you should commit your cluster config at
`management/manifests/argocd/secret-${DEPLOY_NAME}-cluster.yaml`. It is
highly advised to use a secure method to store your secrets. There are many
ways in ArgoCD to achieve this. For more details see their
[Secrets Management][argocd-secrets-mgmt] guide.

Lastly ensure that you've added this secret to your `kustomization.yaml` with
the following:

```bash
cd management/manifests/argocd/
[ ! -f kustomization.yaml ] && kustomize create
kustomize edit add resource secret-${DEPLOY_NAME}-cluster.yaml
```

Now add these files and commit them to your deploy repo. Once this is pushed,
your ArgoCD will see the change and configure itself with your cluster.

## Switching existing UnderStack cluster to a different ArgoCD

To switch to an External ArgoCD for an existing deployment you must first
disable your existing ArgoCD from deleting or updating any applications.

```bash
cat << EOF | kubectl -n argocd patch --type json --patch-file /dev/stdin appset app-of-apps
- op: replace
  path: "/spec/template/spec/syncPolicy/automated/prune"
  value: false
- op: replace
  path: "/spec/template/spec/syncPolicy/automated/selfHeal"
  value: false
EOF
```

Then we must perform the same step but on all the children ApplicationSets
and remove their finalizers.

```bash
for appset in $(kubectl -n argocd get appset -o name); do
    cat << EOF | kubectl -n argocd patch --type json --patch-file /dev/stdin "${appset}"
- op: replace
  path: "/spec/template/spec/syncPolicy/automated/prune"
  value: false
- op: replace
  path: "/spec/template/spec/syncPolicy/automated/selfHeal"
  value: false
- op: remove
  path: "/metadata/finalizers"
EOF
done
```

Now we are ready to remove ArgoCD from our existing cluster.

```bash
kubectl delete ns argocd
```

You are now ready to deploy UnderStack in your external [ArgoCD][argocd].

[argocd]: <https://argo-cd.readthedocs.io/en/stable/>
[argocd-app-of-apps]: <https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/>
[argocd-decl-setup]: <https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/#clusters>
[argocd-secrets-mgmt]: <https://argo-cd.readthedocs.io/en/stable/operator-manual/secret-management/>
