#!/bin/bash

function usage() {
    echo "$(basename "$0") <deploy.env>" >&2
    echo "" >&2
    echo "Generates random secrets needed by the apps in this repo" >&2
    exit 1
}

if ! type -p kubeseal kubectl > /dev/null; then
    echo "You must have kubeseal & kubectl installed to use this script" >&2
    exit 1
fi

if ! $(kubectl api-resources | grep -q sealedsecrets); then
    echo "Your cluster doesn't appear to have the sealed secrets operator installed." >&2
    exit 1
fi

function secret-seal-stdin() {
    # this is meant to be piped to
    # $1 is output file, -w
    kubeseal \
        --scope cluster-wide \
        --allow-empty-data \
        -o yaml \
        -w $1
}

if [ $# -ne 1 ]; then
    usage
fi

SCRIPTS_DIR=$(dirname "$0")

if [ ! -f "$1" ]; then
    echo "Did not get a file with environment variables." >&2
    usage
fi

# set temp path so we can reset it after import
UC_REPO_PATH="$(cd "${SCRIPTS_DIR}" && git rev-parse --show-toplevel)"
export UC_REPO="${UC_REPO_PATH}"

. "$1"

# set the value again after import
export UC_REPO="${UC_REPO_PATH}"

if [ ! -d "${UC_DEPLOY}" ]; then
    echo "UC_DEPLOY not set to a path." >&2
    usage
fi

if [ "x${DEPLOY_NAME}" = "x" ]; then
    echo "DEPLOY_NAME is not set." >&2
    usage
fi

[ -f "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/argocd/secret-deploy.repo.yaml" ] && \
    mv -f "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/argocd/secret-deploy-repo.yaml" "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/cluster/"
if [ -f "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/cluster/secret-deploy-repo.yaml" ]; then
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
export DO_TMPL_VALUES=y
mkdir -p "${UC_DEPLOY}/secrets/${DEPLOY_NAME}"
DEST_DIR="${UC_DEPLOY}/secrets/${DEPLOY_NAME}"

# OpenStack's mariadb secrets
mkdir -p "${DEST_DIR}/openstack/"
[ ! -f "${DEST_DIR}/openstack/secret-mariadb.yaml" ] && \
kubectl --namespace openstack \
    create secret generic mariadb \
    --dry-run=client \
    -o yaml \
    --type Opaque \
    --from-literal=root-password="$(./scripts/pwgen.sh)" \
    --from-literal=password="$(./scripts/pwgen.sh)" \
    | secret-seal-stdin "${DEST_DIR}/openstack/secret-mariadb.yaml"

NAUTOBOT_SECRET_KEY="$(./scripts/pwgen.sh)"
if [ ! -f "${DEST_DIR}/secret-nautobot-django.yaml" ]; then
    kubectl --namespace nautobot \
        create secret generic nautobot-django \
        --dry-run=client \
        -o yaml \
        --type Opaque \
        --from-literal="NAUTOBOT_SECRET_KEY=${NAUTOBOT_SECRET_KEY}" \
        | secret-seal-stdin "${DEST_DIR}/secret-nautobot-django.yaml"
fi

## Dex based SSO Auth. Client Configurations
mkdir -p "${DEST_DIR}/dex/"
# clients generated are in the list below
for client in nautobot argo argocd; do
    if [ ! -f "${DEST_DIR}/dex/secret-nautobot-sso-dex.yaml" ]; then
        SSO_SECRET=$(./scripts/pwgen.sh)
        kubectl --namespace dex \
            create secret generic "${client}-sso" \
            --dry-run=client \
            -o yaml \
            --type Opaque \
            --from-literal=client-secret="$SSO_SECRET" \
            --from-literal=client-id="${client}" \
            --from-literal=issuer="https://dex.${DNS_ZONE}" \
            | secret-seal-stdin "${DEST_DIR}/dex/secret-${client}-sso-dex.yaml"
        unset SSO_SECRET
    fi
done

mkdir -p "${DEST_DIR}/cluster/"

# create constant OpenStack memcache key to avoid cache invalidation on deploy
export MEMCACHE_SECRET_KEY="$(./scripts/pwgen.sh 64)"

## OpenStack component secret generation
## each openstack component is very similar to collapse this
## into a loop to generate the same thing for each
for component in keystone ironic placement neutron nova glance; do
    mkdir -p "${DEST_DIR}/${component}/"
    # keystone service account username
    [ "x${component}" = "xkeystone" ] && keystone_user="admin" || keystone_user="${component}"
    KEYSTONE_USER=$(echo "${keystone_user}" | tr '[:lower:]' '[:upper:]')
    # uppercase the component name to make our variable
    COMPONENT=$(echo "$component" | tr '[:lower:]' '[:upper:]')
    VARNAME_RABBITMQ_PASSWORD="${COMPONENT}_RABBITMQ_PASSWORD"
    VARNAME_DB_PASSWORD="${COMPONENT}_DB_PASSWORD"
    VARNAME_KEYSTONE_PASSWORD="${KEYSTONE_USER}_KEYSTONE_PASSWORD"
    # generate the passwords and set the variable names
    declare "${VARNAME_RABBITMQ_PASSWORD}"="$(./scripts/pwgen.sh)"
    declare "${VARNAME_DB_PASSWORD}"="$(./scripts/pwgen.sh)"
    declare "${VARNAME_KEYSTONE_PASSWORD}"="$(./scripts/pwgen.sh)"
    # export the variables for templating the openstack secret
    export "${VARNAME_RABBITMQ_PASSWORD?}"
    export "${VARNAME_DB_PASSWORD?}"
    export "${VARNAME_KEYSTONE_PASSWORD?}"

    [ ! -f "${DEST_DIR}/${component}/secret-rabbitmq-password.yaml" ] && \
        kubectl --namespace openstack \
        create secret generic "${component}-rabbitmq-password" \
        --type Opaque \
        --from-literal=username="${component}" \
        --from-literal=password="${!VARNAME_RABBITMQ_PASSWORD}" \
        --dry-run=client -o yaml \
        | secret-seal-stdin "${DEST_DIR}/${component}/secret-rabbitmq-password.yaml"

    [ ! -f "${DEST_DIR}/${component}/secret-db-password.yaml" ] && \
        kubectl --namespace openstack \
        create secret generic "${component}-db-password" \
        --type Opaque \
        --from-literal=username="${component}" \
        --from-literal=password="${!VARNAME_DB_PASSWORD}" \
        --dry-run=client -o yaml \
        | secret-seal-stdin "${DEST_DIR}/${component}/secret-db-password.yaml"

    [ ! -f "${DEST_DIR}/${component}/secret-keystone-password.yaml" ] && \
        kubectl --namespace openstack \
        create secret generic "${component}-${keystone_user}-password" \
        --type Opaque \
        --from-literal=username="${keystone_user}" \
        --from-literal=password="${!VARNAME_KEYSTONE_PASSWORD}" \
        --dry-run=client -o yaml \
        | secret-seal-stdin "${DEST_DIR}/openstack/secret-keystone-password.yaml"
done

# horizon credentials
mkdir -p "${DEST_DIR}/horizon"
# horizon user password for database
export HORIZON_DB_PASSWORD="$(./scripts/pwgen.sh)"
[ ! -f "${DEST_DIR}/horizon/secret-db-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic horizon-db-password \
    --type Opaque \
    --from-literal=username="horizon" \
    --from-literal=password="${HORIZON_DB_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/horizon/secret-db-password.yaml"

if [ "x${DO_TMPL_VALUES}" = "xy" ]; then
    [ ! -f "${DEST_DIR}/secret-openstack.yaml" ] && \
    yq '(.. | select(tag == "!!str")) |= envsubst' \
        "./components/openstack-secrets.tpl.yaml" \
        > "${DEST_DIR}/secret-openstack.yaml"
fi

# Argo Events access to RabbitMQ - credentials
for ns in argo-events openstack; do
  [ ! -f "${DEST_DIR}/secret-argo-rabbitmq-password-$ns.yaml" ] && \
  kubectl --namespace $ns \
      create secret generic argo-rabbitmq-password \
      --type Opaque \
      --from-literal=username="argo" \
      --from-literal=password="${ARGO_RABBITMQ_PASSWORD}" \
      --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-argo-rabbitmq-password-$ns.yaml"
done

mkdir -p "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/cluster"
echo "Creating ArgoCD ${DEPLOY_NAME} cluster"
cat << EOF > "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/cluster/secret-${DEPLOY_NAME}-cluster.yaml"
apiVersion: v1
kind: Secret
data:
  config: $(printf '{"tlsClientConfig":{"insecure":false}}' | base64)
  name: $(printf "$DEPLOY_NAME" | base64)
  server: $(printf "https://kubernetes.default.svc" | base64)
metadata:
  name: ${DEPLOY_NAME}-cluster
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: cluster
  annotations:
    uc_repo_git_url: "https://github.com/rackerlabs/understack.git"
    uc_repo_ref: "HEAD"
    uc_deploy_git_url: "$UC_DEPLOY_GIT_URL"
    uc_deploy_ref: "HEAD"
    dns_zone: "$DNS_ZONE"
EOF

if [ "x${NO_SECRET_DEPLOY}" = "x" ]; then
    echo "Creating ArgoCD repo-creds"
    cat << EOF | secret-seal-stdin "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/cluster/secret-deploy-repo.yaml"
apiVersion: v1
kind: Secret
metadata:
  name: ${DEPLOY_NAME}-repo
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: repo-creds
data:
  sshPrivateKey: $(cat "${UC_DEPLOY_SSH_FILE}" | base64 | tr -d '\n')
  type: $(printf "git" | base64)
  url: $(printf "${UC_DEPLOY_GIT_URL}" | base64)
EOF
fi

echo "Creating Cert Manager Cluster Issuer"
[ -f "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/cluster-issuer.yaml" ] && \
    mv -f "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/cluster-issuer.yaml" "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/cluster/"
cat << EOF > "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/cluster/cluster-issuer.yaml"
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

for component in $(find "${DEST_DIR}" -maxdepth 1 -mindepth 1 -type d); do
    if [ ! -f "${component}/kustomization.yaml" ]; then
        pushd "${component}" > /dev/null
        kustomize create --autodetect
        echo "Creating ${component}/kustomization.yaml, don't forget to commit it"
        popd > /dev/null
    fi
done

pushd "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/cluster"
rm -rf kustomization.yaml
kustomize create --autodetect
popd

# Placeholders don't need sealing
if [ ! -f "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/secret-nautobot-custom-env.yaml" ]; then
    echo "Creating nautobot-custom-env secret placeholder"
    kubectl --namespace nautobot \
        create secret generic nautobot-custom-env \
        --dry-run=client \
        -o yaml \
        --type Opaque > "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/secret-nautobot-custom-env.yaml"
fi

exit 0
