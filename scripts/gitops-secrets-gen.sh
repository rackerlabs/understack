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

. "$1"

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

# Nautobot secrets
mkdir -p "${DEST_DIR}/nautobot/"
if [ ! -f "${DEST_DIR}/nautobot/secret-nautobot-django.yaml" ]; then
    kubectl --namespace nautobot \
        create secret generic nautobot-django \
        --dry-run=client \
        -o yaml \
        --type Opaque \
        --from-literal=NAUTOBOT_SECRET_KEY="$(./scripts/pwgen.sh 2>/dev/null)" \
        | secret-seal-stdin "${DEST_DIR}/nautobot/secret-nautobot-django.yaml"
fi

if [ ! -f "${DEST_DIR}/nautobot/secret-nautobot-custom-env.yaml" ]; then
    echo "Creating nautobot-custom-env secret placeholder"
    kubectl --namespace nautobot \
        create secret generic nautobot-custom-env \
        --dry-run=client \
        -o yaml \
        --type Opaque > "${DEST_DIR}/nautobot/secret-nautobot-custom-env.yaml"
fi

if [ ! -f "${DEST_DIR}/nautobot/secret-nautobot-superuser.yaml" ]; then
    # username value comes from the helm chart nautobot.superUser.username
    # email value comes from the helm chart nautobot.superUser.email
    kubectl --namespace nautobot \
        create secret generic nautobot-superuser \
        --dry-run=client \
        -o yaml \
        --type Opaque \
        --from-literal=username=admin \
        --from-literal=email="admin@example.com" \
        --from-literal=password="$(./scripts/pwgen.sh 2>/dev/null)" \
        --from-literal=apitoken="$(./scripts/pwgen.sh 2>/dev/null)" \
        | secret-seal-stdin "${DEST_DIR}/nautobot/secret-nautobot-superuser.yaml"
fi

if [ ! -f "${DEST_DIR}/nautobot/secret-nautobot-redis.yaml" ]; then
    kubectl --namespace nautobot \
        create secret generic nautobot-redis \
        --dry-run=client \
        -o yaml \
        --type Opaque \
        --from-literal=NAUTOBOT_REDIS_PASSWORD="$(./scripts/pwgen.sh 2>/dev/null)" \
        | secret-seal-stdin "${DEST_DIR}/nautobot/secret-nautobot-redis.yaml"
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

if [ ! -f "${DEST_DIR}/cert-manager/cluster-issuer.yaml" ]; then
    echo "Creating cert-manager ClusterIssuer"
    cat <<- EOF > "${DEST_DIR}/cert-manager/cluster-issuer.yaml"
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: ${DEPLOY_NAME}-cluster-issuer
  annotations:
    argocd.argoproj.io/sync-wave: "5"
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
fi

# create constant OpenStack memcache key to avoid cache invalidation on deploy
MEMCACHE_SECRET_KEY=$(cat "${DEST_DIR}/secret-openstack.yaml" 2>/dev/null | yq '.endpoints.oslo_cache.auth.memcache_secret_key')
if [[ $? -ne 0 || "x${MEMCACHE_SECRET_KEY}" = "xnull" ]]; then
    MEMCACHE_SECRET_KEY="$(./scripts/pwgen.sh 64 2>/dev/null)"
fi
export MEMCACHE_SECRET_KEY

# for the secret loading below
set -o pipefail
# for the tr commands below
export LC_ALL=C

convert_to_var_name() {
    echo "$1_$2" | tr '[:lower:]' '[:upper:]'
}

convert_to_secret_name() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | tr '_' '-'
}

## OpenStack component secret generation
## each openstack component is very similar to collapse this
## into a loop to generate the same thing for each
for component in keystone ironic placement neutron nova glance; do
    mkdir -p "${DEST_DIR}/${component}/"
    # keystone service account username
    [ "x${component}" = "xkeystone" ] && keystone_user="admin" || keystone_user="${component}"

    # environment variable names
    VARNAME_RABBITMQ_PASSWORD="$(convert_to_var_name "${component}" "RABBITMQ_PASSWORD")"
    VARNAME_DB_PASSWORD="$(convert_to_var_name "${component}" "DB_PASSWORD")"
    VARNAME_KEYSTONE_PASSWORD="$(convert_to_var_name "${keystone_user}" "KEYSTONE_PASSWORD")"

    # k8s secret names
    SECRET_RABBITMQ_PASSWORD="$(convert_to_secret_name "${VARNAME_RABBITMQ_PASSWORD}")"
    SECRET_DB_PASSWORD="$(convert_to_secret_name "${VARNAME_DB_PASSWORD}")"
    SECRET_KEYSTONE_PASSWORD="$(convert_to_secret_name "${VARNAME_KEYSTONE_PASSWORD}")"

    # attempt to load the existing secrets from the cluster and use those
    # otherwise generate the passwords and set the variable names
    if kubectl -n openstack get secret "${SECRET_RABBITMQ_PASSWORD}" > /dev/null; then
        declare "${VARNAME_RABBITMQ_PASSWORD}"="$(kubectl -n openstack get secret "${SECRET_RABBITMQ_PASSWORD}" -o jsonpath='{.data.password}' | base64 -d)"
        REPLACE_RABBITMQ_PASSWORD=no
    else
        echo "Generating ${SECRET_RABBITMQ_PASSWORD}"
        declare "${VARNAME_RABBITMQ_PASSWORD}"="$(./scripts/pwgen.sh 2>/dev/null)"
        REPLACE_RABBITMQ_PASSWORD=yes
    fi
    if kubectl -n openstack get secret "${SECRET_DB_PASSWORD}" > /dev/null; then
        declare "${VARNAME_DB_PASSWORD}"="$(kubectl -n openstack get secret "${SECRET_DB_PASSWORD}" -o jsonpath='{.data.password}' | base64 -d)"
        REPLACE_DB_PASSWORD=no
    else
        echo "Generating ${SECRET_DB_PASSWORD}"
        declare "${VARNAME_DB_PASSWORD}"="$(./scripts/pwgen.sh 2>/dev/null)"
        REPLACE_DB_PASSWORD=yes
    fi
    if kubectl -n openstack get secret "${SECRET_KEYSTONE_PASSWORD}" > /dev/null; then
        declare "${VARNAME_KEYSTONE_PASSWORD}"="$(kubectl -n openstack get secret "${SECRET_KEYSTONE_PASSWORD}" -o jsonpath='{.data.password}' | base64 -d)"
        REPLACE_KEYSTONE_PASSWORD=no
    else
        echo "Generating ${SECRET_KEYSTONE_PASSWORD}"
        declare "${VARNAME_KEYSTONE_PASSWORD}"="$(./scripts/pwgen.sh 2>/dev/null)"
        REPLACE_KEYSTONE_PASSWORD=yes
    fi
    # export the variables for templating the openstack secret
    export "${VARNAME_RABBITMQ_PASSWORD?}"
    export "${VARNAME_DB_PASSWORD?}"
    export "${VARNAME_KEYSTONE_PASSWORD?}"

    if [ "x${REPLACE_RABBITMQ_PASSWORD}" = "xyes" ]; then
        echo "Writing ${component}/secret-rabbitmq-password.yaml, please commit"
        kubectl --namespace openstack \
        create secret generic "${SECRET_RABBITMQ_PASSWORD}" \
        --type Opaque \
        --from-literal=username="${component}" \
        --from-literal=password="${!VARNAME_RABBITMQ_PASSWORD}" \
        --dry-run=client -o yaml \
        | secret-seal-stdin "${DEST_DIR}/${component}/secret-rabbitmq-password.yaml"
    fi

    if [ "x${REPLACE_DB_PASSWORD}" = "xyes" ]; then
        echo "Writing ${component}/secret-db-password.yaml, please commit"
        kubectl --namespace openstack \
        create secret generic "${SECRET_DB_PASSWORD}" \
        --type Opaque \
        --from-literal=username="${component}" \
        --from-literal=password="${!VARNAME_DB_PASSWORD}" \
        --dry-run=client -o yaml \
        | secret-seal-stdin "${DEST_DIR}/${component}/secret-db-password.yaml"
    fi

    if [ "x${REPLACE_KEYSTONE_PASSWORD}" = "xyes" ]; then
        echo "Writing ${component}/secret-keystone-password.yaml, please commit"
        kubectl --namespace openstack \
        create secret generic "${SECRET_KEYSTONE_PASSWORD}" \
        --type Opaque \
        --from-literal=username="${keystone_user}" \
        --from-literal=password="${!VARNAME_KEYSTONE_PASSWORD}" \
        --dry-run=client -o yaml \
        | secret-seal-stdin "${DEST_DIR}/${component}/secret-keystone-password.yaml"
    fi
done

# horizon credentials
mkdir -p "${DEST_DIR}/horizon"
# horizon user password for database
if kubectl -n openstack get secret "horizon-db-password" > /dev/null; then
    HORIZON_DB_PASSWORD="$(kubectl -n openstack get secret "horizon-db-password" -o jsonpath='{.data.password}' | base64 -d)"
    REPLACE_HORIZON_DB_PASSWORD=no
else
    HORIZON_DB_PASSWORD="$(./scripts/pwgen.sh 2>/dev/null)"
    REPLACE_HORIZON_DB_PASSWORD=yes
fi
export HORIZON_DB_PASSWORD
if [ "x${REPLACE_HORIZON_DB_PASSWORD}" = "xyes" ]; then
    echo "Writing ${component}/secret-keystone-password.yaml, please commit"
    kubectl --namespace openstack \
        create secret generic horizon-db-password \
        --type Opaque \
        --from-literal=username="horizon" \
        --from-literal=password="${HORIZON_DB_PASSWORD}" \
        --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/horizon/secret-db-password.yaml"
fi

# generate the secret-openstack.yaml file every time from our secrets data
# this is a helm values.yaml but it contains secrets because of the lack
# of secrets references in OpenStack Helm
yq '(.. | select(tag == "!!str")) |= envsubst' \
    "./components/openstack-secrets.tpl.yaml" \
    > "${DEST_DIR}/secret-openstack.yaml"

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

# create placeholder directory for metallb configs
mkdir -p "${DEST_DIR}/metallb"

# create a placeholder directory for undersync configs
mkdir -p "${DEST_DIR}/undersync"

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

exit 0
