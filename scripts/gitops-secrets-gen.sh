#!/bin/bash

function usage() {
    echo "$(basename "$0") <deploy.env>" >&2
    echo "" >&2
    echo "Generates random secrets needed by the apps in this repo" >&2
    exit 1
}

if [ $# -ne 1 ]; then
    usage
fi

SCRIPTS_DIR=$(dirname "$0")

if [ ! -f "$1" ]; then
    echo "Did not get a file with environment variables." >&2
    usage
fi

. "$1"

export UC_REPO="$(git rev-parse --show-toplevel)"

if [ ! -d "${UC_DEPLOY}" ]; then
    echo "UC_DEPLOY not set to a path." >&2
    usage
fi

if [ "x${DEPLOY_NAME}" = "x" ]; then
    echo "DEPLOY_NAME is not set." >&2
    usage
fi

if [ -f "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/argocd/secret-deploy-repo.yaml" ]; then
    NO_SECRET_DEPLOY=1
else
    if [ "x${UC_DEPLOY_GIT_URL}" = "x" ]; then
        echo "UC_DEPLOY_GIT_URL is not set." >&2
        usage
    fi
    if [ "x${UC_DEPLOY_SSH_FILE}" = "x" ]; then
        echo "UC_DEPLOY_SSH_FILE is not set." >&2
        usage
    fi
    if [ ! -f "${UC_DEPLOY_SSH_FILE}" ]; then
        echo "UC_DEPLOY_SSH_FILE at ${UC_DEPLOY_SSH_FILE} does not exist." >&2
        usage
    fi
fi

if [ "x${DNS_ZONE}" = "x" ]; then
    echo "DNS_ZONE is not set." >&2
    usage
fi

if [ "x${UC_DEPLOY_EMAIL}" = "x" ]; then
    echo "UC_DEPLOY_EMAIL is not set." >&2
    usage
fi

export DNS_ZONE
export DEPLOY_NAME
export SKIP_KUBESEAL=y
export DO_TMPL_VALUES=y
mkdir -p "${UC_DEPLOY}/secrets/${DEPLOY_NAME}"
"${SCRIPTS_DIR}/easy-secrets-gen.sh" "${UC_DEPLOY}/secrets/${DEPLOY_NAME}"

if [ "x${NO_SECRET_DEPLOY}" = "x" ]; then
    echo "Creating ArgoCD config"
    mkdir -p "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/argocd"
    cat << EOF > "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/argocd/secret-deploy-repo.yaml"
apiVersion: v1
kind: Secret
metadata:
  name: ${DEPLOY_NAME}-repo
  labels:
    argocd.argoproj.io/secret-type: repo-creds
data:
  sshPrivateKey: $(cat "${UC_DEPLOY_SSH_FILE}" | base64 | tr -d '\n')
  type: $(printf "git" | base64)
  url: $(printf "${UC_DEPLOY_GIT_URL}" | base64)
EOF
fi

echo "Creating Cert Manager Cluster Issuer"
cat << EOF > "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/cluster-issuer.yaml"
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: ${DEPLOY_NAME}-cluster-issuer
spec:
  acme:
    email: ${UC_DEPLOY_EMAIL}
    privateKeySecretRef:
      name: letsencrypt-prod
    server: https://acme-v02.api.letsencrypt.org/directory
    solvers:
    - http01:
        ingress:
          ingressClassName: nginx
EOF

echo "Creating metallb secret placeholder"
cat << EOF > "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/secret-metallb.yaml"
---

EOF
