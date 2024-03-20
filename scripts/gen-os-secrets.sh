#!/bin/sh

if [ $# -ne 1 ]; then
    echo "$(basename "$0") <output-file>" >&2
    exit 1
fi

set -o pipefail

if ! type -p yq > /dev/null; then
    echo "You must have yq installed to use this script" >&2
    exit 1
fi

if ! type -p kubectl > /dev/null; then
    echo "You must have kubectl installed to use this script" >&2
    exit 1
fi

KUSTOMIZE_VERSION=$(kubectl version --client -o yaml | yq .kustomizeVersion)
if ! (echo -e "v5.0.0\n$KUSTOMIZE_VERSION" | sort -V -C); then
  echo "kustomize needs to be at version 5.0.0 or newer (comes with kubectl 1.27+)"
  exit 1
fi

SCRIPTS_DIR="$(dirname "$0")"

echo "This script will attempt to look up the existing values this repo used"
echo "or will generate new values. The output below will be related to that."

# keystone admin
export KEYSTONE_ADMIN_PASSWORD=$(kubectl -n openstack get secret keystone-admin -o jsonpath='{.data.password}' | base64 -d || "${SCRIPTS_DIR}/pwgen.sh")
# keystone mariadb
export KEYSTONE_DB_PASSWORD=$(kubectl -n openstack get secret keystone-db-password -o jsonpath='{.data.password}' | base64 -d || "${SCRIPTS_DIR}/pwgen.sh")
# keystone rabbitmq
export KEYSTONE_RABBITMQ_PASSWORD=$(kubectl -n openstack get secret keystone-rabbitmq-password -o jsonpath='{.data.password}' | base64 -d || "${SCRIPTS_DIR}/pwgen.sh")

# ironic keystone service account
export IRONIC_KEYSTONE_PASSWORD=$(kubectl -n openstack get secret ironic-keystone-password -o jsonpath='{.data.password}' | base64 -d || "${SCRIPTS_DIR}/pwgen.sh")
# ironic mariadb
export IRONIC_DB_PASSWORD=$(kubectl -n openstack get secret ironic-db-password -o jsonpath='{.data.password}' | base64 -d || "${SCRIPTS_DIR}/pwgen.sh")
# ironic rabbitmq
export IRONIC_RABBITMQ_PASSWORD=$(kubectl -n openstack get secret ironic-rabbitmq-password -o jsonpath='{.data.password}' | base64 -d || "${SCRIPTS_DIR}/pwgen.sh")

yq '(.. | select(tag == "!!str")) |= envsubst' \
    "${SCRIPTS_DIR}/../components/openstack-secrets.tpl.yaml" \
    > "$1"
