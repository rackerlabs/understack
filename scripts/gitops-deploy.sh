#!/bin/sh

usage() {
    echo "$(basename "$0") <deploy.env>" >&2
    echo "" >&2
    echo "Generates an initial layout of configs for deploying" >&2
    exit 1
}

template() {
    local subvars
    subvars="\$DNS_ZONE \$UC_DEPLOY_GIT_URL \$DEPLOY_NAME"
    cat "$1" | envsubst "${subvars}" > "$2"
}

if [ $# -ne 1 ]; then
    usage
fi

SCRIPTS_DIR="$(dirname "$0")"

if [ ! -f "$1" ]; then
    echo "Did not get a file with environment variables." >&2
    usage
fi

source "$1"

if [ ! -d "${UC_DEPLOY}" ]; then
    echo "UC_DEPLOY not set to a path." >&2
    usage
fi

if [ "x${DEPLOY_NAME}" = "x" ]; then
    echo "DEPLOY_NAME is not set." >&2
    usage
fi

OUTPUT_DIR="${UC_DEPLOY}/clusters/${DEPLOY_NAME}"

export DNS_ZONE
export UC_DEPLOY_GIT_URL
export DEPLOY_NAME

for part in operators components; do
    echo "Creating ${part} configs"
    mkdir -p "${OUTPUT_DIR}/${part}"
    for tmpl in $(find "${SCRIPTS_DIR}/../apps/${part}" -type f); do
        outfile=$(basename "${tmpl}")
        template "${tmpl}" "${OUTPUT_DIR}/${part}/${outfile}"
    done
    rm -rf "${OUTPUT_DIR}/${part}/kustomization.yaml"
done
echo "Creating app-of-apps config"
template "${SCRIPTS_DIR}/../apps/app-of-apps.yaml" "${OUTPUT_DIR}/app-of-apps.yaml"
