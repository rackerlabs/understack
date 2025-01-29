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
# then for each node, we want to delete it and re-enroll it.
# skip nodes which have a customer instance on them.
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
        # check for a customer instance:
        INSTANCE_CHECK=$(openstack baremetal node show "$node_uuid" -f json | jq -r --exit-status '.instance_uuid')

        if [[ $INSTANCE_CHECK != "null" ]]; then
            echo "Node: $node_uuid has an instance. Skipping." ;
        else
            echo "Node: $node_uuid setting ironic maintenance mode" ;
            # set maintenance mode in ironic in case the node is in a status preventing deletion
            openstack baremetal node maintenance set "$node_uuid" ;
            # delete the node
            echo "Node: $node_uuid deleting node in ironic" ;
            openstack baremetal node delete "$node_uuid" ;
        fi
    else
        echo "Node: $node_uuid does not exist in ironic."
    fi

    # issue the enroll-server workflow using the node's drac ip from nautobot
    echo "Node: $node_uuid issuing argo enroll-server workflow" ;
    argo -n argo-events submit --from wftmpl/enroll-server --serviceaccount workflow -p ip_address="$drac_ip"

done
