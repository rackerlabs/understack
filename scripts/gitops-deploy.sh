#!/bin/sh

usage() {
    echo "$(basename "$0") <dns-zone> <deploy-git-repo> <local-clone> <deploy-name>" >&2
    echo "" >&2
    echo "dns-zone: DNS zone where all the ingress endpoints will be hooked to" >&2
    echo "deploy-git-repo: URL to your deploy repo" >&2
    echo "local-clone: path to the local clone of your repo" >&2
    echo "deploy-name: name you are giving your deployment" >&2
    exit 1
}

template() {
    local subvars
    subvars="\$DNS_ZONE \$GIT_URL \$DEPLOY_NAME"
    cat "$1" | envsubst "${subvars}" > "$2"
}

if [ $# -ne 4 ]; then
    usage
fi

SCRIPTS_DIR="$(dirname "$0")"

OUTPUT_DIR="$3"

export DNS_ZONE="$1"
export GIT_URL="$2"
export DEPLOY_NAME="$4"

for part in operators components; do
    echo "Creating ${part} configs"
    mkdir -p "${OUTPUT_DIR}/clusters/${DEPLOY_NAME}/${part}"
    for tmpl in $(find "${SCRIPTS_DIR}/../apps/${part}" -type f); do
        outfile=$(basename "${tmpl}")
        template "${tmpl}" "${OUTPUT_DIR}/clusters/${DEPLOY_NAME}/${part}/${outfile}"
    done
    rm -rf "${OUTPUT_DIR}/clusters/${DEPLOY_NAME}/${part}/kustomization.yaml"
done
echo "Creating app-of-apps config"
template "${SCRIPTS_DIR}/../apps/app-of-apps.yaml" "${OUTPUT_DIR}/clusters/${DEPLOY_NAME}/app-of-apps.yaml"
