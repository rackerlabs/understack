
1. cd python/diff-nautobot-understack
2. python3 -m venv .venv
3. source .venv/bin/activate
4. poetry lock
5. poetry install
6. export nautobot_api_token=<get_token_from_nautobot_dev>  (can be added in .env file too)
7. export nautobot_url=https://nautobot.staging.undercloud.rackspace.net (no need to export for dev env)
8. export OS_CLOUD=uc-dev-infra
9. export OS_CLIENT_CONFIG_FILE=./my_clouds.yaml (set this if it is any other location [defined here](https://opendev.org/openstack/openstacksdk#getting-started))

- Below are some example commands
```
    uc-diff --help
    uc-diff project undercloud -v
    uc-diff network
```
