#!/usr/bin/env bash

function usage() {
    echo "$(basename "$0") <nautobot.cab.name>" >&2
    echo "" >&2
    echo "Rekicks ironic baremetal nodes in the specified cabinet" >&2
    echo "" >&2
    echo "Example: $(basename "$0") F20-3" >&2
    echo "" >&2
    echo "Required environment variables:" >&2
    echo "" >&2
    echo "NAUTOBOT_URL= URL to the nautobot instance" >&2
    echo "NAUTOBOT_TOKEN= Nautobot authentication token for API use" >&2
    echo "OS_CLOUD= OpenStack cloud config to use for ironic baremetal node management (infra)" >&2
    echo "" >&2

    exit 1
}

# check for inputs and required environment variables

if [[ -z "${NAUTOBOT_TOKEN}" ]]; then
    echo "Error: NAUTOBOT_TOKEN environment variable not found."
    usage
fi

if [[ -z "${NAUTOBOT_URL}" ]]; then
    echo "Error: NAUTOBOT_URL environment variable not found."
    usage
fi

if [[ -z "${OS_CLOUD}" ]]; then
    echo "Error: OS_CLOUD environment variable not found."
    usage
fi

if [[ -z "$1" ]]; then
    echo "Error: Rack not specified"
    echo ""
    usage
fi

RACK="$1"

IFS=$'\n'

# uses the nbgql.sh helper script to query nautobot's graphql api,
# then for each node, enroll it if it doesn't already exisst in ironic.
for item in $(./nbgql.sh nautobot_graphql_queries/get_hosts_in_rack.gql "$RACK" | jq -c -r '.data.devices[]') ; do
    echo "" ;
    node_uuid=$(jq -r '.id' <<< "$item");
    name=$(jq -r '.name' <<< "$item");
    drac_ip=$(jq -r '.interfaces[0].ip_addresses[0].host' <<< "$item") ;
    echo "working on node: $node_uuid name: $name drac: $drac_ip ";

    # check if node is in ironic
    # shellcheck disable=SC2034
    NODE_CHECK=$(openstack baremetal node show "$node_uuid" -f json)
    EXIT_STATUS=$?
    if [ $EXIT_STATUS -eq 0 ]; then
        echo "Node: $node_uuid exists in ironic. Skipping." ;
    else
        echo "Node: $node_uuid does not exist in ironic."
        # issue the enroll-server workflow using the node's drac ip from nautobot
        echo "Node: $node_uuid issuing argo enroll-server workflow" ;
        argo -n argo-events submit --from wftmpl/enroll-server --serviceaccount workflow -p ip_address="$drac_ip"
    fi

done
