#!/usr/bin/env bash

function usage() {
    echo "$(basename "$0") graphql_query_file.gql [variable]" >&2
    echo "" >&2
    echo "Queries Nautobot GraphQL API using the GQL input file with an optional variable to be substituted in your gql." >&2
    echo "" >&2
    echo "Required environment variables:" >&2
    echo "" >&2
    echo "NAUTOBOT_URL= URL to the nautobot instance" >&2
    echo "NAUTOBOT_TOKEN= Nautobot authentication token for API use" >&2
    echo "" >&2
    echo "Query files available include:" >&2
    ls "`dirname "$0"`"/nautobot_graphql_queries/*.gql >&2
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

if [[ -z "$1" ]]; then
    echo "Error: GraphQL template not specified."
    echo ""
    usage
fi

IFS=$'\n'

# read the gql query from the file named in the argument
# QUERY_VARIABLE can be used in gql templates along with
# envsubst for the variable substitution
# shellcheck disable=SC2034
QUERY_VARIABLE="$2"

# shellcheck disable=SC2086
QUERY=$(jq -n \
           --arg q "$(cat $1 | envsubst | tr -d '\n')" \
           '{ query: $q }')

# perform the nautobot graphql query
curl -s -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Token $NAUTOBOT_TOKEN" \
  --data "$QUERY" \
  "${NAUTOBOT_URL}/api/graphql/"
