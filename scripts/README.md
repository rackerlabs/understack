# UnderStack Scripts

## Setup


UnderStack scripts and tools use the following environment variables for configuration:

``` bash
# Nautobot instance URL
export NAUTOBOT_URL=https://nautobot.dev.understack
# Nautobot token
export NAUTOBOT_TOKEN=0123456789abcdefghijklmnopqrstuvwxyz
# OpenStack cloud credentials
export OS_CLOUD=understack-dev
```

There are also a number of CLI tools we use:

* [OpenStack CLI Setup](https://rackerlabs.github.io/understack/user-guide/openstack-cli/)
* [Argo Workflows CLI Setup](https://rackerlabs.github.io/understack/component-argo-workflows/?h=argo#argo-cli)

For more about OpenStack cloud configuration, see: <https://rackerlabs.github.io/understack/user-guide/openstack-cli/>

For more about Nautobot tokens, see: <https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/users/token/>

The Argo Workflows CLI uses your current `kubectl` config context to access the kubernetes cluster
and argo workflows.

## nbgql.sh

Query Nautobot's GraphQL API using a query template in the `nautobot_graphql_queries` directory.

For example, to find the servers in the rack named "F20-3", you can run:

``` bash
./nbgql.sh nautobot_graphql_queries/get_hosts_in_rack.gql F20-3
```

## rekick-rack.sh

Rekicks the servers in the specified Nautobot rack name.

For example, to rekick the servers in the rack named "F20-3", you can run:

``` bash
./rekick-rack.sh F20-3
```
