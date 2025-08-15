# pwsafe_credentials.py
import json
import os
import requests
import json
import sys

from ansible.module_utils.basic import AnsibleModule

IDENTITY_TOKEN = os.getenv("IDENTITY_TOKEN")
PWSAFE_ENDPOINT = os.getenv("PASSWORD_SAFE_URL")

def get_credentials(project_id, usernames, descriptions):
    headers = {"Accept": "application/json", "X-AUTH-TOKEN": IDENTITY_TOKEN}
    credentials = []

    page = 1
    while True:
        url = f"{PWSAFE_ENDPOINT}/projects/{project_id}/credentials.json?page={page}"
        try:
            response = requests.get(url, headers=headers, verify=False, timeout=10)
        except requests.RequestException as e:
            sys.exit(f"Request failed: {e}")

        if response.status_code != 200:
            sys.exit(f"Request failed with status {response.status_code}")

        data = response.json()
        if not data:
            break

        credentials.extend(data)
        page += 1

    return _filter_service_accounts(credentials, usernames, descriptions)


def _filter_service_accounts(credentials, usernames, descriptions):
    service_accounts = []
    for item in credentials:
        cred = item.get("credential", {})
        if (
            cred.get("category") == "Service Accounts"
            and cred.get("username") in usernames
            and cred.get("description") in descriptions
        ):
            try:
                json_pwd = json.loads(cred["password"])
                service_accounts.append({
                    "username": cred["username"],
                    "password": json_pwd.get("password"),
                    "token": json_pwd.get("token"),
                })
            except (KeyError, json.JSONDecodeError):
                continue
    return service_accounts


def build_description(env, username):
    return f"{env} nautobot {username} user"


def run_module():
    module_args = dict(
        usernames=dict(type='list', required=True),
        project_id=dict(type='str', required=True),
        env=dict(type='str', required=True),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)
    usernames = module.params['usernames']
    descriptions = [build_description("dev", username) for username in usernames]
    credentials = get_credentials(module.params['project_id'], usernames, descriptions)

    missing = [u for u in usernames if u not in [c["username"] for c in credentials]]

    result = dict(
        changed=False,
        credentials=credentials,
        missing_usernames=missing,
        all_credentials_found=(len(missing) == 0),
    )
    module.exit_json(**result)

if __name__ == '__main__':
    run_module()
