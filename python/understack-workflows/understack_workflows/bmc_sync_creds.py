import requests
import json
from typing import List, Dict
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FACTORY_PASSWORD = "calvin"
FACTORY_USER = "root"

def sync_creds(ip_address, required_password, logger, username="root"):
    """Access BMC via redfish and change password from factory default if needed

    We try the standard password.

    If that doesn't work we try the factory default password, if that succeeds
    then we set the password to our standard one.
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
    """Test whether provided credentials work against a secured API endpoint"""
    try:
        r = _redfish_request(host, "/redfish/v1", username, password)
        account_service_uri = r["AccountService"]["@odata.id"]
        _redfish_request(host, account_service_uri, username, password)
        return True
    except Exception as e:
        logger.warning(f"Exception: {e}")
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
    try:
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
    try:
        r = requests.request(
            method, f"https://{host}{uri}", verify=False, auth=(username, password), timeout=15, json=payload
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        raise
