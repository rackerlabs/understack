#!/usr/bin/env bash

function usage() {
    # shellcheck disable=SC2005
    echo "$(basename "$0")" >&2
    echo "" >&2
    echo "Resync keystone projects in to nautobot by updating the keystone project's description" >&2
    echo "" >&2
    echo "Required environment variables:" >&2
    echo "" >&2
    echo "OS_CLOUD= OpenStack cloud config to use for ironic baremetal node management (infra)" >&2
    echo "" >&2

    exit 1
}

# check for inputs and required environment variables
if [[ -z "${OS_CLOUD}" ]]; then
    echo "Error: OS_CLOUD environment variable not found."
    usage
fi

IFS=$'\n'

# We'll append a string `update-${TIMESTAMP}` to help us
# keep track of when the project was last updated.
TIMESTAMP=$(date -u +"%Y%m%d%H%M%S")

# For each keystone project, we want to trigger the keystone->argo workflow->nautobot sync,
# which we can do by updating the description of the project.
for item in $(openstack project list --long --domain default -f json | jq -c -r '.[]') ; do
    PROJECT_ID=$(jq -r '.ID' <<< "$item");
    PROJECT_NAME=$(jq -r '.Name' <<< "$item");
    DESCRIPTION=$(jq -r '.Description' <<< "$item");
    NEW_DESCRIPTION="$DESCRIPTION update-$TIMESTAMP"
    # Grab the last word of the current description to check if
    # it's the update timestamp.
    last_word=$(echo "$DESCRIPTION" | awk '{print $NF}')
    if [[ $last_word == update-* ]]; then
        # The description has suffix update-{timestamp} already.
        # This replaces the old update timestamp with the new one.
        TMP=$(echo "$DESCRIPTION" | awk '{$NF=""; sub(/[ \t]+$/, ""); print}')
        NEW_DESCRIPTION="$TMP update-$TIMESTAMP"
    fi
    # strip preceding whitespaces if necessary
    # shellcheck disable=SC2001
    NEW_DESCRIPTION=$(echo "$NEW_DESCRIPTION" | sed 's/^[ \t]*//')

    echo "Updating: Project: $PROJECT_NAME ($PROJECT_ID)";
    echo "Old description: $DESCRIPTION";
    echo "New description: $NEW_DESCRIPTION";
    openstack project set --domain default "$PROJECT_ID" --description "$NEW_DESCRIPTION"
    echo "---"
done
