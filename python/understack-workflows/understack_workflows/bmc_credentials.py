import requests
import json
from typing import List, Dict
import urllib3
from understack_workflows.helpers import setup_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FACTORY_PASSWORD = "calvin"
FACTORY_USER = "root"

logger = setup_logger(__name__)

class HttpAuthorisationFailed(Exception):
    """Specifically for 401 errors"""

def set_bmc_password(ip_address, required_password, username="root"):
    """Access BMC via redfish and change password from factory default if needed

    Check that we can log in using the standard password.

    If that doesn't work, try the factory default password, if that succeeds
    then we change the BMC password to our standard one.

    Once the password has been changed then we check that it works by logging in
    again.

    Raises an Exception if the password is not confirmed working.
    """
    if _verify_auth(ip_address, username, required_password):
        logger.info("Production BMC credentials are working on this BMC.")
        return

    logger.info(
        "Production BMC credentials don't work on this BMC. "
        "Trying factory default credentials."
    )
    if not _verify_auth(ip_address, username, FACTORY_PASSWORD):
        raise Exception(
            f"Unable to log in to BMC {ip_address} with any known password!"
        )

    _set_bmc_creds(
        ip_address, FACTORY_USER, FACTORY_PASSWORD, username, required_password
    )
    logger.info("BMC password has been set.")

    if _verify_auth(ip_address, username, required_password):
        logger.info("Production BMC credentials are working on this BMC.")



def _verify_auth(host: str, username: str = "root", password: str = "") -> bool:
    """Test whether provided credentials work against a secured API endpoint

    Returns true on success, False on authorisation failure and raises an
    Exception for  other kinds of errors (e.g. timeout, etc)
    """
    try:
        r = _redfish_request(host, "/redfish/v1", username, password)
        account_service_uri = r.get("AccountService", {}).get("@odata.id")
        if account_service_uri is None:
            raise Exception(
                "Unrecognised redfish response, missing AccountService URI"
            )
        _redfish_request(host, account_service_uri, username, password)
        return True
    except HttpAuthorisationFailed as e:
        logger.warning(e)
        return False


def _get_bmc_accounts(host: str, username: str, password: str) -> List[Dict]:
    """A vendor agnostic approach to crawling the API for BMC accounts"""
    try:
        # get account service
        r = _redfish_request(host, "/redfish/v1", username, password)
        account_service_uri = r["AccountService"]["@odata.id"]
        logger.debug(f"account_service_url: {account_service_uri}")

        # get account collection uri
        r = _redfish_request(host, account_service_uri, username, password)
        accounts_uri = r["Accounts"]["@odata.id"]
        logger.debug(f"accounts_url: {accounts_uri}")

        # get accounts
        r = _redfish_request(host, accounts_uri, username, password)
        accounts = r["Members"]
        logger.debug(f"accounts: {accounts}")

        return accounts
    except Exception:
        logger.exception("Unable to fetch accounts from Redfish account service.")
        raise


def _set_bmc_creds(host: str, username: str, password: str, required_username: str, required_password: str):
    """Find the account associated with the username in question"""
    accounts = _get_bmc_accounts(host, username, password)

    matched_account = None
    for account in accounts:
        account_url = account["@odata.id"]

        a = _redfish_request(host, account_url, username, password)
        if required_username == a["UserName"]:
            logger.debug(f"found account: {a}")
            matched_account = a
            break

    if not matched_account:
        raise Exception(f"Unable to find BMC account for {required_username}")

    account_uri = matched_account["@odata.id"]

    payload = {"Password": required_password}
    _redfish_request(host, account_uri, username, password, "PATCH", payload)

def _redfish_request(
    host: str, uri: str, username: str, password: str, method: str = "GET", payload: Dict | None = None
) -> dict:
    url = f"https://{host}{uri}"
    try:
        response = requests.request(
            method, url, verify=False, auth=(username, password), timeout=15, json=payload
        )
        if response.status_code == 401:
            raise HttpAuthorisationFailed(f"Redfish HTTP 401 from {uri}")

        response.raise_for_status()
        return response.json()
    except Exception:
        raise
