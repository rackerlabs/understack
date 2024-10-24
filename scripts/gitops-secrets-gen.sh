#!/bin/bash

# get the failure from the command that failed in a pipe
set -o pipefail

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
if ! kubectl wait --for condition=established --timeout=30s crd/sealedsecrets.bitnami.com ; then
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
        -w "$1"
}

if [ $# -ne 1 ]; then
    usage
fi

SCRIPTS_DIR=$(dirname "$0")

if [ ! -f "$1" ]; then
    echo "Did not get a file with environment variables." >&2
    usage
fi

# shellcheck disable=SC1090
. "$1"

if [ ! -d "${UC_DEPLOY}" ]; then
    echo "UC_DEPLOY not set to a path." >&2
    usage
fi

if [ -z "${DEPLOY_NAME}" ]; then
    echo "DEPLOY_NAME is not set." >&2
    usage
fi

if [ -z "${DNS_ZONE}" ]; then
    echo "DNS_ZONE is not set." >&2
    usage
fi

export DNS_ZONE
export DEPLOY_NAME
DEST_DIR="${UC_DEPLOY}/${DEPLOY_NAME}/manifests"
mkdir -p "${DEST_DIR}"

###
### start of secrets for each component
###

# create ArgoCD configs
function gen-argocd() {
    mkdir -p "${DEST_DIR}/argocd"
    echo "Checking argocd"
    if [ ! -f "${DEST_DIR}/argocd/secret-${DEPLOY_NAME}-cluster.yaml" ]; then
        echo "Creating ArgoCD ${DEPLOY_NAME} cluster"
        if [ -z "${UC_DEPLOY_GIT_URL}" ]; then
            echo "UC_DEPLOY_GIT_URL is not set." >&2
            usage
        fi
        cat <<- EOF > "${DEST_DIR}/argocd/secret-${DEPLOY_NAME}-cluster.yaml"
apiVersion: v1
kind: Secret
data:
  config: $(printf '{"tlsClientConfig":{"insecure":false}}' | base64)
  name: $(printf '%s' "$DEPLOY_NAME" | base64)
  server: $(printf "https://kubernetes.default.svc" | base64)
metadata:
  name: ${DEPLOY_NAME}-cluster
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: cluster
    understack.rackspace.com/argocd: enabled
  annotations:
    uc_repo_git_url: "https://github.com/rackerlabs/understack.git"
    uc_repo_ref: "HEAD"
    uc_deploy_git_url: "$UC_DEPLOY_GIT_URL"
    uc_deploy_ref: "HEAD"
    dns_zone: "$DNS_ZONE"
EOF
    fi

    if [ ! -f "${DEST_DIR}/argocd/secret-deploy-repo.yaml" ]; then
        echo "Creating ArgoCD repo-creds"
        if [ -z "${UC_DEPLOY_GIT_URL}" ]; then
            echo "UC_DEPLOY_GIT_URL is not set." >&2
            usage
        fi
        if [ -z "${UC_DEPLOY_SSH_FILE}" ]; then
            echo "UC_DEPLOY_SSH_FILE is not set." >&2
            usage
        fi
        if [ ! -f "${UC_DEPLOY_SSH_FILE}" ]; then
            echo "UC_DEPLOY_SSH_FILE at ${UC_DEPLOY_SSH_FILE} does not exist." >&2
            usage
        fi
        cat << EOF | secret-seal-stdin "${DEST_DIR}/argocd/secret-deploy-repo.yaml"
apiVersion: v1
kind: Secret
metadata:
  name: ${DEPLOY_NAME}-repo
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: repo-creds
data:
  sshPrivateKey: $(base64 < "${UC_DEPLOY_SSH_FILE}" | tr -d '\n')
  type: $(printf "git" | base64)
  url: $(printf '%s' "${UC_DEPLOY_GIT_URL}" | base64)
EOF
    fi
}

[ -n "${UC_AIO}" ] && gen-argocd || echo "UC_AIO is NOT set so not creating ArgoCD bits"

echo "Checking cert-manager"
mkdir -p "${DEST_DIR}/cert-manager"
if [ ! -f "${DEST_DIR}/cert-manager/cluster-issuer.yaml" ]; then
    if [ "${UC_DEPLOY_EMAIL}" = "" ]; then
        echo "UC_DEPLOY_EMAIL is not set. Unable to generate cert-manager issuer." >&2
        usage
    fi

    echo "Creating cert-manager ClusterIssuer"
    cat <<- EOF > "${DEST_DIR}/cert-manager/cluster-issuer.yaml"
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: understack-cluster-issuer
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

echo "Checking metallb"
# create placeholder directory for metallb configs
mkdir -p "${DEST_DIR}/metallb"

echo "Checking nautobot"
# Nautobot secrets
mkdir -p "${DEST_DIR}/nautobot/"
if [ ! -f "${DEST_DIR}/nautobot/secret-nautobot-django.yaml" ]; then
    kubectl --namespace nautobot \
        create secret generic nautobot-django \
        --dry-run=client \
        -o yaml \
        --type Opaque \
        --from-literal=NAUTOBOT_SECRET_KEY="$("${SCRIPTS_DIR}/pwgen.sh" 2>/dev/null)" \
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
        --from-literal=password="$("${SCRIPTS_DIR}/pwgen.sh" 2>/dev/null)" \
        --from-literal=apitoken="$("${SCRIPTS_DIR}/pwgen.sh" 2>/dev/null)" \
        | secret-seal-stdin "${DEST_DIR}/nautobot/secret-nautobot-superuser.yaml"
fi

if [ ! -f "${DEST_DIR}/nautobot/secret-nautobot-redis.yaml" ]; then
    kubectl --namespace nautobot \
        create secret generic nautobot-redis \
        --dry-run=client \
        -o yaml \
        --type Opaque \
        --from-literal=NAUTOBOT_REDIS_PASSWORD="$("${SCRIPTS_DIR}/pwgen.sh" 2>/dev/null)" \
        | secret-seal-stdin "${DEST_DIR}/nautobot/secret-nautobot-redis.yaml"
fi

echo "Checking dex"
## Dex based SSO Auth. Client Configurations
mkdir -p "${DEST_DIR}/dex/"
# clients generated are in the list below
for client in nautobot argo argocd keystone grafana; do
    if [ ! -f "${DEST_DIR}/dex/secret-${client}-sso-dex.yaml" ]; then
        SSO_SECRET=$("${SCRIPTS_DIR}/pwgen.sh")
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

echo "Checking openstack"
# OpenStack's mariadb secrets
mkdir -p "${DEST_DIR}/openstack/"
[ ! -f "${DEST_DIR}/openstack/secret-mariadb.yaml" ] && \
kubectl --namespace openstack \
    create secret generic mariadb \
    --dry-run=client \
    -o yaml \
    --type Opaque \
    --from-literal=root-password="$("${SCRIPTS_DIR}/pwgen.sh")" \
    --from-literal=password="$("${SCRIPTS_DIR}/pwgen.sh")" \
    | secret-seal-stdin "${DEST_DIR}/openstack/secret-mariadb.yaml"

# create constant OpenStack memcache key to avoid cache invalidation on deploy
MEMCACHE_SECRET_KEY=$(yq '.endpoints.oslo_cache.auth.memcache_secret_key' < "${DEST_DIR}/secret-openstack.yaml")
if [[ $? -ne 0 || "${MEMCACHE_SECRET_KEY}" = "null" ]]; then
    MEMCACHE_SECRET_KEY="$("${SCRIPTS_DIR}/pwgen.sh" 64 2>/dev/null)"
fi
export MEMCACHE_SECRET_KEY

# for the tr commands below
export LC_ALL=C

convert_to_var_name() {
    echo "$1_$2" | tr '[:lower:]' '[:upper:]'
}

convert_to_secret_name() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | tr '_' '-'
}

load_or_gen_os_secret() {
    local data_var=$1
    local secret_var=$2

    if kubectl -n openstack get secret "${secret_var}" &>/dev/null; then
        data="$(kubectl -n openstack get secret "${secret_var}" -o jsonpath='{.data.password}' | base64 -d)"
        # good ol' bash 3 compat for macOS
        eval "${data_var}=\"${data}\""
        # return 1 because we have an existing secret
        return 1
    else
        echo "Generating ${secret_var}"
        data="$("${SCRIPTS_DIR}/pwgen.sh" 2>/dev/null)"
        # good ol' bash 3 compat for macOS
        eval "${data_var}=\"${data}\""
        # return 0 because we need to write this out
        return 0
    fi
}

create_os_secret() {
    local name=$1
    local component=$2
    local username=$3
    local secret_var="SECRET_${name}"
    local data_var="VARNAME_${name}"
    local password_var="${!data_var}"
    file_suffix=$(convert_to_secret_name "${name}")

    echo "Writing ${component}/secret-${file_suffix}.yaml, please commit"
    kubectl --namespace openstack \
    create secret generic "${!secret_var}" \
    --type Opaque \
    --from-literal=username="${username}" \
    --from-literal=password="${!password_var}" \
    --dry-run=client -o yaml \
    | secret-seal-stdin "${DEST_DIR}/${component}/secret-${file_suffix}.yaml"
}

## OpenStack component secret generation
## each openstack component is very similar to collapse this
## into a loop to generate the same thing for each
for component in keystone ironic placement neutron nova glance; do
    echo "Checking ${component}"
    mkdir -p "${DEST_DIR}/${component}/"
    # keystone service account username
    [ "${component}" = "keystone" ] && keystone_user="admin" || keystone_user="${component}"

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
    load_or_gen_os_secret "${VARNAME_RABBITMQ_PASSWORD}" "${SECRET_RABBITMQ_PASSWORD}" && \
        create_os_secret "RABBITMQ_PASSWORD" "${component}" "${component}"
    load_or_gen_os_secret "${VARNAME_DB_PASSWORD}" "${SECRET_DB_PASSWORD}" && \
        create_os_secret "DB_PASSWORD" "${component}" "${component}"
    load_or_gen_os_secret "${VARNAME_KEYSTONE_PASSWORD}" "${SECRET_KEYSTONE_PASSWORD}" && \
        create_os_secret "KEYSTONE_PASSWORD" "${component}" "${keystone_user}"

    # export the variables for templating the openstack secret
    export "${VARNAME_RABBITMQ_PASSWORD?}"
    export "${VARNAME_DB_PASSWORD?}"
    export "${VARNAME_KEYSTONE_PASSWORD?}"

done

echo "Checking horizon"
# horizon credentials
mkdir -p "${DEST_DIR}/horizon"
# horizon user password for database
VARNAME_DB_PASSWORD="HORIZON_DB_PASSWORD"
SECRET_DB_PASSWORD="horizon-db-password"
load_or_gen_os_secret "${VARNAME_DB_PASSWORD}" "${SECRET_DB_PASSWORD}" && \
    create_os_secret "DB_PASSWORD" "horizon" "horizon"
# export the variable for templating into the openstack secret / values.yaml
export HORIZON_DB_PASSWORD

# generate the secret-openstack.yaml file every time from our secrets data
# this is a helm values.yaml but it contains secrets because of the lack
# of secrets references in OpenStack Helm
yq '(.. | select(tag == "!!str")) |= envsubst' \
    "${SCRIPTS_DIR}/../components/openstack-secrets.tpl.yaml" \
    > "${DEST_DIR}/secret-openstack.yaml"

echo "Checking undersync"
# create a placeholder directory for undersync configs
mkdir -p "${DEST_DIR}/undersync"

find "${DEST_DIR}" -maxdepth 1 -mindepth 1 -type d | while read -r component; do
    if [ ! -f "${component}/kustomization.yaml" ]; then
        pushd "${component}" > /dev/null || exit 1
        kustomize create --autodetect
        echo "Creating ${component}/kustomization.yaml, don't forget to commit it"
        popd > /dev/null || exit 1
    fi
done

exit 0
