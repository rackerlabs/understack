# Nautobot vs OpenStack Comparison Tool

This tool compares data between Nautobot and OpenStack.

## Currently Supported Comparisons

| OpenStack | Nautobot              |
|-----------|-----------------------|
| Project   | Tenant                |
| Network   | UCVNI & Namespace     |


---

## Setup Instructions

1. cd python/diff-nautobot-understack
2. python3 -m venv .venv
3. source .venv/bin/activate
4. poetry lock
5. poetry install
6. Export environment variables (or add them to a .env file):
   1. export NAUTOBOT_TOKEN=<get_token_from_nautobot_dev>
   2. export NAUTOBOT_URL=https://nautobot.staging.undercloud.rackspace.net (no need to export for dev env)
   3. export OS_CLOUD=uc-dev-infra
   4. export OS_CLIENT_CONFIG_FILE=./my_clouds.yaml (set this if it is in any other location not [defined here](https://opendev.org/openstack/openstacksdk#getting-started))


- Below are some example commands
```
    uc-diff --help
    uc-diff project undercloud -v
    uc-diff network
```
