#!/usr/bin/env bash

# Check arguments
if [ "$#" -ne 1 ]; then
    echo "$(basename "$0") <output-file>" >&2
    exit 1
fi

# Enable safer bash settings
set -o pipefail

# Check dependencies
if ! command -v yq >/dev/null; then
    echo "You must have yq installed to use this script" >&2
    exit 1
fi

if ! command -v kubectl >/dev/null; then
    echo "You must have kubectl installed to use this script" >&2
    exit 1
fi

# Get kustomize version (declare/assign separately)
KUSTOMIZE_VERSION=""
KUSTOMIZE_VERSION=$(kubectl version --client -o yaml | yq '.kustomizeVersion')
if ! (printf '%s\n' "v5.0.0" "$KUSTOMIZE_VERSION" | sort -V -C); then
    echo "kustomize needs to be at version 5.0.0 or newer (comes with kubectl 1.27+)"
    exit 1
fi

# Scripts directory
SCRIPTS_DIR=""
SCRIPTS_DIR=$(dirname "$0")

echo "This script will attempt to look up the existing values this repo used"
echo "or will generate new values. The output below will be related to that."

# memcache secret key
MEMCACHE_SECRET_KEY=""
MEMCACHE_SECRET_KEY=$("${SCRIPTS_DIR}/pwgen.sh" 64)
export MEMCACHE_SECRET_KEY

# keystone admin
KEYSTONE_ADMIN_PASSWORD=""
KEYSTONE_ADMIN_PASSWORD=$(kubectl -n openstack get secret keystone-admin \
  -o jsonpath='{.data.password}' | base64 -d || "${SCRIPTS_DIR}/pwgen.sh")
export KEYSTONE_ADMIN_PASSWORD

# keystone mariadb
KEYSTONE_DB_PASSWORD=""
KEYSTONE_DB_PASSWORD=$(kubectl -n openstack get secret keystone-db-password \
  -o jsonpath='{.data.password}' | base64 -d || "${SCRIPTS_DIR}/pwgen.sh")
export KEYSTONE_DB_PASSWORD

# keystone rabbitmq
KEYSTONE_RABBITMQ_PASSWORD=""
KEYSTONE_RABBITMQ_PASSWORD=$(kubectl -n openstack get secret keystone-rabbitmq-password \
  -o jsonpath='{.data.password}' | base64 -d || "${SCRIPTS_DIR}/pwgen.sh")
export KEYSTONE_RABBITMQ_PASSWORD

# ironic keystone service account
IRONIC_KEYSTONE_PASSWORD=""
IRONIC_KEYSTONE_PASSWORD=$(kubectl -n openstack get secret ironic-keystone-password \
  -o jsonpath='{.data.password}' | base64 -d || "${SCRIPTS_DIR}/pwgen.sh")
export IRONIC_KEYSTONE_PASSWORD

# ironic mariadb
IRONIC_DB_PASSWORD=""
IRONIC_DB_PASSWORD=$(kubectl -n openstack get secret ironic-db-password \
  -o jsonpath='{.data.password}' | base64 -d || "${SCRIPTS_DIR}/pwgen.sh")
export IRONIC_DB_PASSWORD

# ironic rabbitmq
IRONIC_RABBITMQ_PASSWORD=""
IRONIC_RABBITMQ_PASSWORD=$(kubectl -n openstack get secret ironic-rabbitmq-password \
  -o jsonpath='{.data.password}' | base64 -d || "${SCRIPTS_DIR}/pwgen.sh")
export IRONIC_RABBITMQ_PASSWORD

# Generate output
yq '(.. | select(tag == "!!str")) |= envsubst' \
    "${SCRIPTS_DIR}/../components/openstack-secrets.tpl.yaml" \
    > "$1"
