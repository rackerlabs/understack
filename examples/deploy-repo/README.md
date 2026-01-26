# deploy-repo

This is an example of a Deployment Repo per the documentation.

It defines all 3 environment types:

- Management
- Global
- Site

The Management is in the `mgmt` directory. The Global is in the
`global` directory. With one Site in `site`.

## Quick Test

The following will stand up 3 test clusters.

```bash
./scripts/e2e-test-setup.sh setup
```

Then you can switch to the `mgmt` cluster.

```bash
kubectl ctx kind-mgmt
```

Then load the ArgoCD configuration.

```bash
kustomize build --load-restrictor LoadRestrictionsNone \
  ./examples/deploy-repo/mgmt/apps/argocd/ \
  | kubectl -n argocd apply -f -
```

Now get access to ArgoCD.

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d
```

```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

Go to <http://127.0.0.1:8080>
