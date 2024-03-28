#!/bin/sh

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

kubectl --namespace openstack \
    create secret generic mariadb \
    --dry-run=client -o yaml \
    --type Opaque \
    --from-literal=root-password="$(${SCRIPTS_DIR}/pwgen.sh)" \
    --from-literal=password="$(${SCRIPTS_DIR}/pwgen.sh)" \
    > "$1/secret-mariadb.yaml"

kubectl --namespace nautobot \
    create secret generic nautobot-env \
    --dry-run=client -o yaml \
    --type Opaque \
    --from-literal=NAUTOBOT_SECRET_KEY="$(${SCRIPTS_DIR}/pwgen.sh)" \
    --from-literal=NAUTOBOT_SUPERUSER_API_TOKEN="$(${SCRIPTS_DIR}/pwgen.sh)" \
    --from-literal=NAUTOBOT_SUPERUSER_PASSWORD="$(${SCRIPTS_DIR}/pwgen.sh)" \
    > "$1/secret-nautobot-env.yaml"

kubectl --namespace nautobot \
    create secret generic nautobot-redis \
    --dry-run=client -o yaml \
    --type Opaque \
    --from-literal=redis-password="$(${SCRIPTS_DIR}/pwgen.sh)" \
    > "$1/secret-nautobot-redis.yaml"

"${SCRIPTS_DIR}/gen-os-secrets.sh" "$1/secret-openstack.yaml"
