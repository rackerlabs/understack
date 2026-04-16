# Standard Library
import os

# Third Party
import requests


def query_nautobot_graphql(query):
    nautobot_token = os.environ.get("NAUTOBOT_TOKEN")
    if not nautobot_token:
        raise RuntimeError("A Nautobot Token is required")
    nautobot_url = os.environ.get("NAUTOBOT_URL")
    if not nautobot_url:
        raise RuntimeError("A Nautobot URL is required")
    headers = {
        "Authorization": f"Token {nautobot_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    res = requests.post(
        f"{nautobot_url}/api/graphql/", headers=headers, json={"query": query}
    )
    res.raise_for_status()
    return res
