from ansible.module_utils.basic import AnsibleModule
import requests


def get_existing_token(base_url, username, password, user_token, module):
    headers = {"Accept": "application/json"}
    tokens_url = f"{base_url}/api/users/tokens/"

    try:
        response = requests.get(tokens_url, headers=headers, auth=(username, password))
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        module.fail_json(
            msg=f"Failed to fetch existing tokens for user {username}: {str(e)}"
        )

    tokens = response.json().get("results", [])
    return next((t for t in tokens if t.get("key") == user_token), None)


def create_new_token(base_url, username, password, user_token, description, module):
    """Create a new Nautobot token using Basic Auth."""
    tokens_url = f"{base_url}/api/users/tokens/"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    payload = {"key": user_token, "description": description, "write_enabled": True}

    try:
        response = requests.post(
            tokens_url, headers=headers, json=payload, auth=(username, password)
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        module.fail_json(
            msg=f"Failed to create new token for user {username}: {str(e)}"
        )

    return response.json()


def run_module():
    module_args = dict(
        base_url=dict(type="str", required=True),
        username=dict(type="str", required=True),
        password=dict(type="str", required=True, no_log=True),
        user_token=dict(type="str", required=True, no_log=True),
        token_description=dict(type="str", default="ansible-created-token"),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    base_url = module.params["base_url"].rstrip("/")
    username = module.params["username"]
    password = module.params["password"]
    user_token = module.params["user_token"]
    token_description = module.params["token_description"]

    # fetch existing token
    token = get_existing_token(base_url, username, password, user_token, module)
    if token:
        module.exit_json(
            changed=False,
            username=username,
            message=f"Found existing Nautobot token for user {username}",
        )

    # No token found → try creating new
    new_token = create_new_token(
        base_url, username, password, user_token, token_description, module
    )
    if not new_token:
        module.fail_json(msg=f"Failed to create new token for user {username}")

    module.exit_json(
        changed=True,
        username=username,
        message=f"No token found, created new Nautobot token for user {username}",
    )


def main():
    run_module()


if __name__ == "__main__":
    main()
