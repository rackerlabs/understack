#!/bin/bash -e

cd $(git rev-parse --show-toplevel)

DEST_DIR=${1:-.}

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
for ns in nautobot dex; do
  [ ! -f "${DEST_DIR}/secret-nautobot-sso-$ns.yaml" ] && \
  kubectl --namespace $ns \
    create secret generic nautobot-sso \
    --dry-run=client \
    -o yaml \
    --type Opaque \
    --from-literal=client-secret="$NAUTOBOT_SSO_SECRET" \
    | secret-seal-stdin "${DEST_DIR}/secret-nautobot-sso-$ns.yaml"
done
unset NAUTOBOT_SSO_SECRET

ARGO_SSO_SECRET=$(./scripts/pwgen.sh)
for ns in argo argo-events dex; do
  [ ! -f "${DEST_DIR}/secret-argo-sso-$ns.yaml" ] && \
  kubectl --namespace $ns \
    create secret generic argo-sso \
    --dry-run=client \
    -o yaml \
    --type Opaque \
    --from-literal=client-secret="$ARGO_SSO_SECRET" \
    --from-literal=client-id=argo \
    | secret-seal-stdin "${DEST_DIR}/secret-argo-sso-$ns.yaml"
done
unset ARGO_SSO_SECRET

ARGOCD_SSO_SECRET=$(./scripts/pwgen.sh)
for ns in argocd dex; do
  [ ! -f "${DEST_DIR}/secret-argocd-sso-$ns.yaml" ] && \
  kubectl --namespace $ns \
    create secret generic argocd-sso \
    --dry-run=client \
    -o yaml \
    --type Opaque \
    --from-literal=issuer="https://dex.${DNS_ZONE}" \
    --from-literal=client-secret="$ARGOCD_SSO_SECRET" \
    --from-literal=client-id=argocd \
    | yq '.metadata.labels |= {"app.kubernetes.io/part-of": "argocd"}' \
    | secret-seal-stdin "${DEST_DIR}/secret-argocd-sso-$ns.yaml"
done
unset ARGOCD_SSO_SECRET

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

if [ "x${DO_TMPL_VALUES}" = "xy" ]; then
    [ ! -f "${DEST_DIR}/secret-openstack.yaml" ] && \
    yq '(.. | select(tag == "!!str")) |= envsubst' \
        "./components/openstack-secrets.tpl.yaml" \
        > "${DEST_DIR}/secret-openstack.yaml"
fi

cd ${DEST_DIR}
rm -f kustomization.yaml
kustomize create --autodetect
cd -
