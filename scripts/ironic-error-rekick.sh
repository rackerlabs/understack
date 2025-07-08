#!/usr/bin/env bash

function usage() {
    # shellcheck disable=SC2005
    echo "$(basename "$0")" >&2
    echo "" >&2
    echo "Rekicks ironic baremetal nodes in 'error' status" >&2
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

# Query the nodes and find the ones in error state which have no instances.
for item in $(openstack baremetal node list -f json | jq -c -r '.[]') ; do
    NODE_UUID=$(jq -r '.UUID' <<< "$item");
    NODE_STATE=$(jq -r '."Provisioning State"' <<< "$item");
    NODE_INSTANCE=$(jq -r '."Instance UUID"' <<< "$item");
    if [[ "$NODE_STATE" == "error" && "$NODE_INSTANCE" == "null" ]]; then
        NODE_IP=$(openstack baremetal node show "$NODE_UUID" -f json | jq -c -r '.driver_info.redfish_address' | sed 's|https://||g');
        echo "NODE: $NODE_UUID ($NODE_IP) is in ERROR state and has no instance on it. Rekicking...";
        echo "NODE: $NODE_UUID Setting maintenance mode...";
        openstack baremetal node maintenance set "$NODE_UUID"
        echo "NODE: $NODE_UUID Deleting from ironic...";
        openstack baremetal node delete "$NODE_UUID"
        echo "NODE: $NODE_UUID Submitting re-enroll workflow...";
        argo -n argo-events submit --from wftmpl/enroll-server --serviceaccount workflow -p ip_address="$NODE_IP"
    fi
done
