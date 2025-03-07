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
2. `poetry install`
   1. poetry will handle the creation of this virtual environment for you. It'll use .venv in the project if you configure it to do so locally on your machine with `poetry config virtualenvs.in-project true`.
   2. user can create a shell with poetry shell and then when they exit it will clean up auth variables. Or they can run source .venv/bin/activate or poetry run <commands-below>

3. Export environment variables (or add them to a .env file):
   1. export NAUTOBOT_URL=https://nautobot.url.here
   2.   users should browse to https://nautobot.url.here/user/api-tokens/ and generate an API token
   3. export NAUTOBOT_TOKEN= <generated token from above step>
   4. export OS_CLOUD=uc-dev-infra
   5. export OS_CLIENT_CONFIG_FILE=./my_clouds.yaml (set this if it is in any other location not [defined here](https://opendev.org/openstack/openstacksdk#getting-started))


- Below are some example commands
```
    uc-diff --help
    uc-diff project undercloud -v
    uc-diff network
```
