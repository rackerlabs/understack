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

Rekicks the servers in the specified Nautobot rack name, while skipping
rekicking any nodes which have customer instances on them.

For example, to rekick the servers in the rack named "F20-3", you can run:

``` bash
./rekick-rack.sh F20-3
```

## enroll-missing-nodes.sh

``` text
./enroll-missing-nodes.sh <rack>
```

Rekicks the servers in the specified Nautobot rack name.

For example, to enroll any missing servers in the rack named "F20-3", you can run:

``` bash
./enroll-missing-nodes.sh F20-3
```

## audit_ports_missing_physical_network.py

Audits Neutron ports whose `binding_profile` contains `local_link_information`
but is missing `physical_network`.

The script defaults to a fast report-only mode. In this mode it uses a
field-limited Neutron port list and does not query Ironic, so the
`BAREMETAL_PORT_PHYSICAL_NETWORK` column is empty.

Add `--derive-baremetal-port-physical-network` to look up matching Ironic
baremetal ports and populate the `BAREMETAL_PORT_PHYSICAL_NETWORK` column.
This is slower because it performs the baremetal lookup for each matching
Neutron port.

Add `--execute` to write the baremetal port `physical_network` back into the
Neutron port's `binding_profile`. `--execute` implies
`--derive-baremetal-port-physical-network`.

The script prints a tab-separated table:

``` text
NODE_ID  PORT_ID  NAME  NETWORK_ID  BAREMETAL_PORT_PHYSICAL_NETWORK  REASON
```

Status messages, including the final scanned/matched count, are printed to
stderr.

Recommended workflow for one cloud:

``` bash
# Fast inventory of affected Neutron ports.
./scripts/audit_ports_missing_physical_network.py --os-cloud uc-iad3-dev

# Slower report that also shows the Ironic baremetal port physical_network
# that would be used for repair.
./scripts/audit_ports_missing_physical_network.py \
  --os-cloud uc-iad3-dev \
  --derive-baremetal-port-physical-network

# Repair fixable ports.
./scripts/audit_ports_missing_physical_network.py --os-cloud uc-iad3-dev --execute
```

Run the environments in this order:

``` bash
./scripts/audit_ports_missing_physical_network.py --os-cloud uc-iad3-dev
./scripts/audit_ports_missing_physical_network.py --os-cloud uc-iad3-dev --execute
./scripts/audit_ports_missing_physical_network.py --os-cloud uc-iad3-staging --execute
./scripts/audit_ports_missing_physical_network.py --os-cloud uc-dfw3-prod --execute
```

In `--execute` mode, unresolved ports stay in the table with an empty
`BAREMETAL_PORT_PHYSICAL_NETWORK` and a `REASON`. They are logged as warnings;
only actual update failures are treated as hard errors.
