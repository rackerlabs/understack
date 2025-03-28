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
2. `uv sync`
   1. `uv` will handle the creation of this virtual environment for you. It'll use .venv in the project.
   2. user can create a shell with `uv shell` and then when they exit it will clean up auth variables. Or they can run source .venv/bin/activate or `uv run <commands-below>`

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
