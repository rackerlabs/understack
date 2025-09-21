from ansible.module_utils.basic import AnsibleModule
import requests


def check_existing_token(base_url, username, password, user_token):
    """Check if a specific token exists for the user."""
    headers = {"Accept": "application/json"}
    tokens_url = f"{base_url}/api/users/tokens/"

    try:
        response = requests.get(tokens_url, headers=headers, auth=(username, password))
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return None, f"Failed to fetch tokens: {e}"

    data = response.json()
    tokens = data.get("results", [])

    if not tokens:
        return None, "No tokens found"

    # Find the token matching user_token
    token = next((t for t in tokens if t.get("key") == user_token), None)
    if not token:
        return None, "Specified token not found for user"

    return token, None


def create_new_token(
    base_url, username, password, user_token, description="ansible-created-token"
):
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
        return None, f"Failed to create new token: {e}"

    return response.json(), None


def run_module():
    module_args = dict(
        base_url=dict(type="str", required=True),
        username=dict(type="str", required=True),
        password=dict(type="str", required=True, no_log=True),
        user_token=dict(type="str", required=True, no_log=True),
        create_if_notfound=dict(type="bool", default=True),
        token_description=dict(type="str", default="ansible-created-token"),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)
    result = dict(changed=False, token=None, message="")

    base_url = module.params["base_url"].rstrip("/")
    username = module.params["username"]
    password = module.params["password"]
    user_token = module.params["user_token"]
    create_if_notfound = module.params["create_if_notfound"]
    token_description = module.params["token_description"]

    if module.check_mode:
        module.exit_json(**result)

    # Check existing token
    token, error = check_existing_token(base_url, username, password, user_token)

    if token:
        result.update(
            changed=False,
            message=f"Found existing token for {username}",
            token=dict(
                id=str(token.get("id")),
                display=str(token.get("display")),
                created=str(token.get("created")),
                expires=str(token.get("expires")),
                write_enabled=bool(token.get("write_enabled")),
                description=str(token.get("description", "No description")),
            ),
        )
        module.exit_json(**result)

    # No token found → create new if allowed
    if create_if_notfound:
        new_token, err = create_new_token(
            base_url, username, password, user_token, token_description
        )
        if err:
            module.fail_json(msg=err)
        result.update(
            changed=True,
            message=f"No token found, created new token for {username}",
            token=new_token,
        )
        module.exit_json(**result)

    # No token and not allowed to create → fail
    module.fail_json(msg=f"No token found for {username} and creation disabled")


def main():
    run_module()


if __name__ == "__main__":
    main()
