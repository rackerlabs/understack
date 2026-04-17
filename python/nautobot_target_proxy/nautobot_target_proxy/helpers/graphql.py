# Standard Library
import os

# Third Party
import requests


def get_required_env_var(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def query_nautobot_graphql(query, variables=None):
    nautobot_token = get_required_env_var("NAUTOBOT_TOKEN")
    nautobot_url = os.environ.get("NAUTOBOT_URL")
    if not nautobot_url:
        raise RuntimeError("A Nautobot URL is required")
    headers = {
        "Authorization": f"Token {nautobot_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    res = requests.post(
        f"{nautobot_url}/api/graphql/",
        headers=headers,
        json={"query": query, "variables": variables or {}},
    )
    res.raise_for_status()
    return res
