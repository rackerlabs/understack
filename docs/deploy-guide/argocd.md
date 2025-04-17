# ArgoCD

Unlike the [Quick Start](./gitops-install.md) you will not want to run
ArgoCD, the deployment tool/engine on the same cluster hosting your workload.
In most cases you will not want to run ArgoCD, the deployment tool/engine on
the same cluster that is hosting your workload. The [Quick Start](./gitops-install.md)
used the [apps/aio-app-of-apps.yaml][aio-app-of-apps] to initialize ArgoCD
using the [App of Apps pattern][argo-app-of-apps].

## An existing deployment

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

You are now ready to deploy UnderStack in your external ArgoCD.

## Deploying UnderStack in an external ArgoCD

If you did not have UnderStack already deployed with an ArgoCD in cluster
or you followed the removal steps above, you are ready for this section.

Firstly you must create a cluster configuration for the UnderStack
[App of Apps][app-of-apps] which can be done by treating your
setup like an [extra region](./extra-regions.md). Once you've created
your cluster config and loaded it into your ArgoCD then you can load the
UnderStack [app-of-apps] into your ArgoCD with:

```bash
kubectl -n argocd apply -f apps/app-of-apps.yaml
```

If you followed the [Quick Start](./gitops-install.md), you will notice the
slightly different filename. The leading `aio` is removed which stands for
All In One.

[aio-app-of-apps]: <https://github.com/rackerlabs/understack/blob/main/apps/aio-app-of-apps.yaml>
[app-of-apps]: <https://github.com/rackerlabs/understack/blob/main/apps/app-of-apps.yaml>
[argo-app-of-apps]: <https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/>
