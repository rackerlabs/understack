import argparse
import json
import os
import sys

import requests
from helpers import credential

from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Switch auto-sync status on an Application",
    )
    parser.add_argument(
        "--automated-sync",
        type=bool,
        required=True,
        help="Requested state of automated sync",
    )
    parser.add_argument(
        "--app-name", type=str, required=True, help="Name of the Application"
    )

    return parser


APP_NAME = "understack"
REQUEST_TIMEOUT_LOGIN = 30
REQUEST_TIMEOUT_PATCH = 10
# TODO: we may need to change this to True and provide appropriate CA certificate
VERIFY_SSL = False
if not VERIFY_SSL:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def argocd_credentials():
    """Reads ArgoCD server, username, and password from mounted secret files."""
    argocd_server_host = credential(APP_NAME, "server_host")
    argocd_user = credential(APP_NAME, "user")
    argocd_pass = credential(APP_NAME, "password")

    if not all([argocd_server_host, argocd_user, argocd_pass]):
        logger.error(
            "One or more ArgoCD credentials are empty after reading from secret."
        )
        sys.exit(1)
    return argocd_server_host, argocd_user, argocd_pass


def get_argocd_token(session, api_base_url, username, password):
    """Logs into ArgoCD and returns an authentication token."""
    logger.info("Logging into ArgoCD...")
    session_url = f"{api_base_url}/session"
    login_data = {"username": username, "password": password}

    try:
        response = session.post(
            session_url, json=login_data, timeout=REQUEST_TIMEOUT_LOGIN
        )
        response.raise_for_status()
        token_data = response.json()
        token = token_data.get("token")
        if not token:
            logger.error("Failed to retrieve ArgoCD token from login response.")
            sys.exit(1)
        logger.debug("Successfully obtained ArgoCD token.")
        return token
    except requests.exceptions.RequestException as e:
        logger.error("ArgoCD login failed: %s", e)
        sys.exit(1)


def patch_argocd_application(session, api_base_url, app_name, token, action):
    """Patches the specified ArgoCD application."""
    app_patch_url = f"{api_base_url}/applications/{app_name}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "patchType": "application/merge-patch+json",
        "patch": '{"spec": {"syncPolicy": {"automated": {"selfHeal": action}}}}',
    }
    logger.debug(
        "Patching Application '%(app_name)s' to '%(action)s'.Payload: %(payload)s",
        extra=dict(app_name=app_name, action=action, payload=json.dumps(payload)),
    )

    try:
        response = session.patch(
            app_patch_url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT_PATCH
        )
        response.raise_for_status()
        logger.debug(
            "Successfully patched Application '%(app_name)s'. "
            "Action: '%(action)s'. Status: %(code)s",
            extra=dict(action=action, app_name=app_name, code=response.status_code),
        )
        return True
    except requests.exceptions.RequestException as e:
        logger.error("Failed to patch ArgoCD Application '%s': %s", app_name, e)
        if hasattr(e, "response") and e.response is not None:
            logger.error("Error Response: %s", e.response.text)
        return False


def main():
    """Switch auto-sync status on an Application.

    This updates an Application syncPolicy to a requested state.
    """
    args = argument_parser().parse_args()

    action = "enable" if args.automated_sync else "disable"
    logger.info(
        "changing syncPolicy to '%s' for ArgoCD Application: %s", action, args.app_name
    )

    argocd_server_host, argocd_user, argocd_pass = argocd_credentials()
    api_base_url = f"https://{argocd_server_host}/api/v1"
    logger.info("ArgoCD API URL: %s, User: %s", api_base_url, argocd_user)

    with requests.Session() as http_session:
        http_session.verify = VERIFY_SSL
        token = get_argocd_token(http_session, api_base_url, argocd_user, argocd_pass)

        if not patch_argocd_application(
            http_session, api_base_url, args.app_name, token, args.automated_sync
        ):
            sys.exit(1)

    logger.info(
        "Action '%s' completed successfully for Application '%s'.",
        action,
        args.app_name,
    )


if __name__ == "__main__":
    main()
