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

[ ! -f "${DEST_DIR}/secret-mariadb.yaml" ] && \
kubectl --namespace openstack \
    create secret generic mariadb \
    --dry-run=client \
    -o yaml \
    --type Opaque \
    --from-literal=root-password="$(./scripts/pwgen.sh)" \
    --from-literal=password="$(./scripts/pwgen.sh)" \
    | secret-seal-stdin "${DEST_DIR}/secret-mariadb.yaml"

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

[ ! -f "${DEST_DIR}/secret-nautobot-redis.yaml" ] && \
kubectl --namespace nautobot \
    create secret generic nautobot-redis \
    --dry-run=client \
    -o yaml \
    --type Opaque \
    --from-literal=redis-password="$(./scripts/pwgen.sh)" \
    | secret-seal-stdin "${DEST_DIR}/secret-nautobot-redis.yaml"

NAUTOBOT_SSO_SECRET=$(./scripts/pwgen.sh)
[ ! -f "${DEST_DIR}/secret-nautobot-sso-dex.yaml" ] && \
kubectl --namespace dex \
  create secret generic nautobot-sso \
  --dry-run=client \
  -o yaml \
  --type Opaque \
  --from-literal=client-secret="$NAUTOBOT_SSO_SECRET" \
  --from-literal=client-id=nautobot \
  | secret-seal-stdin "${DEST_DIR}/secret-nautobot-sso-dex.yaml"
unset NAUTOBOT_SSO_SECRET

ARGO_SSO_SECRET=$(./scripts/pwgen.sh)
[ ! -f "${DEST_DIR}/secret-argo-sso-dex.yaml" ] && \
kubectl --namespace dex \
  create secret generic argo-sso \
  --dry-run=client \
  -o yaml \
  --type Opaque \
  --from-literal=client-secret="$ARGO_SSO_SECRET" \
   --from-literal=client-id=argo \
  | secret-seal-stdin "${DEST_DIR}/secret-argo-sso-dex.yaml"
unset ARGO_SSO_SECRET

ARGOCD_SSO_SECRET=$(./scripts/pwgen.sh)
[ ! -f "${DEST_DIR}/secret-argocd-sso-dex.yaml" ] && \
kubectl --namespace dex \
  create secret generic argocd-sso \
  --dry-run=client \
  -o yaml \
  --type Opaque \
  --from-literal=issuer="https://dex.${DNS_ZONE}" \
  --from-literal=client-secret="$ARGOCD_SSO_SECRET" \
  --from-literal=client-id=argocd \
  | secret-seal-stdin "${DEST_DIR}/secret-argocd-sso-dex.yaml"
unset ARGOCD_SSO_SECRET
mkdir -p "${DEST_DIR}/cluster/"

# create constant OpenStack memcache key to avoid cache invalidation on deploy
export MEMCACHE_SECRET_KEY="$(./scripts/pwgen.sh 64)"
# keystone admin user password
export KEYSTONE_ADMIN_PASSWORD="$(./scripts/pwgen.sh)"
# keystone user password in mariadb for keystone db
export KEYSTONE_DB_PASSWORD="$(./scripts/pwgen.sh)"
# rabbitmq user password for the keystone queues
export KEYSTONE_RABBITMQ_PASSWORD="$(./scripts/pwgen.sh)"
# ironic keystone service account
export IRONIC_KEYSTONE_PASSWORD="$(./scripts/pwgen.sh)"
# ironic user password in mariadb for ironic db
export IRONIC_DB_PASSWORD="$(./scripts/pwgen.sh)"
# rabbitmq user password for the ironic queues
export IRONIC_RABBITMQ_PASSWORD="$(./scripts/pwgen.sh)"
# neutron keystone service account
export NEUTRON_KEYSTONE_PASSWORD="$(./scripts/pwgen.sh)"
# neutron user password in mariadb for neutron db
export NEUTRON_DB_PASSWORD="$(./scripts/pwgen.sh)"
# rabbitmq user password for the neutron queues
export NEUTRON_RABBITMQ_PASSWORD="$(./scripts/pwgen.sh)"
# nova keystone service account
export NOVA_KEYSTONE_PASSWORD="$(./scripts/pwgen.sh)"
# nova user password in mariadb for nova db
export NOVA_DB_PASSWORD="$(./scripts/pwgen.sh)"
# rabbitmq user password for the inovaronic queues
export NOVA_RABBITMQ_PASSWORD="$(./scripts/pwgen.sh)"
# placement keystone service account
export PLACEMENT_KEYSTONE_PASSWORD="$(./scripts/pwgen.sh)"
# placement user password in mariadb for placement db
export PLACEMENT_DB_PASSWORD="$(./scripts/pwgen.sh)"
# horizon user password for database
export HORIZON_DB_PASSWORD="$(./scripts/pwgen.sh)"
# glance keystone service account
export GLANCE_KEYSTONE_PASSWORD="$(./scripts/pwgen.sh)"
# glance user password in mariadb for glance db
export GLANCE_DB_PASSWORD="$(./scripts/pwgen.sh)"
# rabbitmq user password for the glance queues
export GLANCE_RABBITMQ_PASSWORD="$(./scripts/pwgen.sh)"

[ ! -f "${DEST_DIR}/secret-keystone-rabbitmq-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic keystone-rabbitmq-password \
    --type Opaque \
    --from-literal=username="keystone" \
    --from-literal=password="${KEYSTONE_RABBITMQ_PASSWORD}" \
    --dry-run=client -o yaml \
    | secret-seal-stdin "${DEST_DIR}/secret-keystone-rabbitmq-password.yaml"

[ ! -f "${DEST_DIR}/secret-keystone-db-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic keystone-db-password \
    --type Opaque \
    --from-literal=password="${KEYSTONE_DB_PASSWORD}" \
    --dry-run=client -o yaml \
    | secret-seal-stdin "${DEST_DIR}/secret-keystone-db-password.yaml"

[ ! -f "${DEST_DIR}/secret-keystone-admin.yaml" ] && \
kubectl --namespace openstack \
    create secret generic keystone-admin \
    --type Opaque \
    --from-literal=password="${KEYSTONE_ADMIN_PASSWORD}" \
    --dry-run=client -o yaml \
    | secret-seal-stdin "${DEST_DIR}/secret-keystone-admin.yaml"

# ironic credentials
[ ! -f "${DEST_DIR}/secret-ironic-rabbitmq-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic ironic-rabbitmq-password \
    --type Opaque \
    --from-literal=username="ironic" \
    --from-literal=password="${IRONIC_RABBITMQ_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-ironic-rabbitmq-password.yaml"

[ ! -f "${DEST_DIR}/secret-ironic-db-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic ironic-db-password \
    --type Opaque \
    --from-literal=password="${IRONIC_DB_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-ironic-db-password.yaml"

[ ! -f "${DEST_DIR}/secret-ironic-keystone-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic ironic-keystone-password \
    --type Opaque \
    --from-literal=username="ironic" \
    --from-literal=password="${IRONIC_KEYSTONE_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-ironic-keystone-password.yaml"

# neutron credentials
[ ! -f "${DEST_DIR}/secret-neutron-rabbitmq-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic neutron-rabbitmq-password \
    --type Opaque \
    --from-literal=username="neutron" \
    --from-literal=password="${NEUTRON_RABBITMQ_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-neutron-rabbitmq-password.yaml"

[ ! -f "${DEST_DIR}/secret-neutron-db-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic neutron-db-password \
    --type Opaque \
    --from-literal=password="${NEUTRON_DB_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-neutron-db-password.yaml"

[ ! -f "${DEST_DIR}/secret-neutron-keystone-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic neutron-keystone-password \
    --type Opaque \
    --from-literal=username="neutron" \
    --from-literal=password="${NEUTRON_KEYSTONE_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-neutron-keystone-password.yaml"

# nova credentials
[ ! -f "${DEST_DIR}/secret-nova-rabbitmq-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic nova-rabbitmq-password \
    --type Opaque \
    --from-literal=username="nova" \
    --from-literal=password="${NOVA_RABBITMQ_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-nova-rabbitmq-password.yaml"

[ ! -f "${DEST_DIR}/secret-nova-db-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic nova-db-password \
    --type Opaque \
    --from-literal=password="${NOVA_DB_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-nova-db-password.yaml"

[ ! -f "${DEST_DIR}/secret-nova-keystone-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic nova-keystone-password \
    --type Opaque \
    --from-literal=username="nova" \
    --from-literal=password="${NOVA_KEYSTONE_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-nova-keystone-password.yaml"

# placement credentials
[ ! -f "${DEST_DIR}/secret-placement-keystone-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic placement-keystone-password \
    --type Opaque \
    --from-literal=username="placement" \
    --from-literal=password="${PLACEMENT_KEYSTONE_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-placement-keystone-password.yaml"

[ ! -f "${DEST_DIR}/secret-placement-db-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic placement-db-password \
    --type Opaque \
    --from-literal=password="${PLACEMENT_DB_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-placement-db-password.yaml"

# horizon credentials
[ ! -f "${DEST_DIR}/secret-horizon-db-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic horizon-db-password \
    --type Opaque \
    --from-literal=password="${HORIZON_DB_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-horizon-db-password.yaml"

# glance credentials
[ ! -f "${DEST_DIR}/secret-glance-rabbitmq-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic glance-rabbitmq-password \
    --type Opaque \
    --from-literal=username="glance" \
    --from-literal=password="${GLANCE_RABBITMQ_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-glance-rabbitmq-password.yaml"

[ ! -f "${DEST_DIR}/secret-glance-db-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic glance-db-password \
    --type Opaque \
    --from-literal=password="${GLANCE_DB_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-glance-db-password.yaml"

[ ! -f "${DEST_DIR}/secret-glance-keystone-password.yaml" ] && \
kubectl --namespace openstack \
    create secret generic glance-keystone-password \
    --type Opaque \
    --from-literal=username="glance" \
    --from-literal=password="${GLANCE_KEYSTONE_PASSWORD}" \
    --dry-run=client -o yaml | secret-seal-stdin "${DEST_DIR}/secret-glance-keystone-password.yaml"

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

pushd "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/cluster"
rm -rf kustomization.yaml
kustomize create --autodetect
popd

# Placeholders don't need sealing
if [ ! -f "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/secret-nautobot-env.yaml" ]; then
    echo "Creating nautobot-env secret placeholder"
    kubectl --namespace nautobot \
        create secret generic nautobot-env \
        --dry-run=client \
        -o yaml \
        --type Opaque > "${UC_DEPLOY}/secrets/${DEPLOY_NAME}/secret-nautobot-env.yaml"
fi

exit 0
