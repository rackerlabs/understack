# Extra Regions

To create extra regions the operation will be very similar to
creating the initial Understack deployment.

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

## Secret Creation

To avoid defining many environment variables we'll simplify by creating an
`.env` file for our deployment. In this case we'll call it `my-region.env` and
place it where we've cloned understack. A complete file would look like:

```bash title="/path/to/uc-deploy/my-region.env"
# this can remain as the literal value and will ensure it computes the right path
UC_DEPLOY="$(cd "$(dirname ${BASH_SOURCE[0]})" && git rev-parse --show-toplevel)"
DEPLOY_NAME="my-region"
DNS_ZONE=home.lab
UC_DEPLOY_EMAIL="my@email"
NO_ARGOCD=yes
```

Secrets in their very nature are sensitive pieces of data. The ultimate
storage and injection of these in a production environment needs to be
carefully considered. For the purposes of this document, Sealed Secrets
has been chosen; other tools like Vault, SOPS, etc should be considered
for production deployments.

```bash
# from your understack checkout
./scripts/gitops-secrets-gen.sh ${UC_DEPLOY}/my-region.env
pushd "${UC_DEPLOY}"
git add my-region
git commit -m "my-region: secrets generation"
popd
```

## Generating a cluster config

Now you must generate a configuration for your cluster, which will need to
live where you deploy ArgoCD Applications. Within this repos scripts that
would be `$UC_DEPLOY/$MAIN_DEPLOY/secrets/argocd/` and then you must
add the file to the `kustomization.yaml` resources.

```bash title="generating a cluster config"
(
source ${UC_DEPLOY}/my-region.env

cat << EOF > cluster-config.yaml
apiVersion: v1
kind: Secret
metadata:
  name: ${DEPLOY_NAME}-cluster
  namespace: argocd
  annotations:
    uc_repo_git_url: https://github.com/rackerlabs/understack.git
    uc_repo_ref: HEAD
    uc_deploy_git_url: "${UC_DEPLOY_GIT_URL}"
    uc_deploy_ref: HEAD
    dns_zone: "${DNS_ZONE}"
  labels:
    argocd.argoproj.io/secret-type: cluster
type: Opaque
data:
  name: $(printf "%s" "${DEPLOY_NAME}" | base64)
  server: BASE64_URL
  config: |
    BASE64_CONTENTS
EOF
)
```

This unfortunately does not give a working cluster config. You must determine
what the correct process is for ArgoCD to authenticate and access your other
regional cluster. For information on how to do this see
[ArgoCD Declarative Setup][argocd-decl-setup].

Once you've completed your cluster config you can run it through `kubeseal`
with:

```bash
cat cluster-config.yaml | kubeseal -o yaml -w $UC_DEPLOY/$MAIN_DEPLOY/secrets/argocd/secret-my-region-cluster.yaml
```

[gitops]: <https://about.gitlab.com/topics/gitops/>
[argocd-decl-setup]: <https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/#clusters>
