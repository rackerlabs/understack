#!/bin/bash

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

SCRIPTS_DIR=$(dirname "$0")

if [ ! -f "$1" ]; then
    echo "Did not get a file with environment variables." >&2
    usage
fi

# set temp path so we can reset it after import
UC_REPO_PATH="$(cd "${SCRIPTS_DIR}" && git rev-parse --show-toplevel)"

# shellcheck disable=SC1090
. "$1"

# set the value again after import
export UC_REPO="${UC_REPO_PATH}"

if [ ! -d "${UC_REPO}" ]; then
    echo "UC_REPO not set to a path." >&2
    usage
fi

if [ ! -d "${UC_DEPLOY}" ]; then
    echo "UC_DEPLOY not set to a path." >&2
    usage
fi

if [ "x${DEPLOY_NAME}" = "x" ]; then
    echo "DEPLOY_NAME is not set." >&2
    usage
fi

UC_REPO_COMPONENTS="${UC_REPO}/components"
UC_DEPLOY_HELM_CFG="${UC_DEPLOY}/${DEPLOY_NAME}/helm-configs"

export DNS_ZONE
export UC_DEPLOY_GIT_URL
export DEPLOY_NAME

# create helm-configs directory for values.yaml overrides
mkdir -p "${UC_DEPLOY_HELM_CFG}"
for component in dex; do
    helmvals="${UC_DEPLOY_HELM_CFG}/${component}.yaml"
    if [ -f "${helmvals}" ]; then
        echo "You have ${helmvals} already, not overwriting"
        continue
    fi
    if  [ -f "${UC_REPO_COMPONENTS}/${component}/values.tpl.yaml" ]; then
            template "${UC_REPO_COMPONENTS}/${component}/values.tpl.yaml" "${helmvals}"
    else
        echo "# add your values.yaml overrides for the helm chart here" > "${helmvals}"
    fi
done
