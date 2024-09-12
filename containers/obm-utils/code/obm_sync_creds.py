import logging
import os
import sys
import argparse
import requests
import time
import json
from typing import List, Dict
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


def redfish_request(
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


def verify_auth(host: str, username: str = "root", password: str = "") -> bool:
    """Verify auth credentials against a secured API endpoint"""
    try:
        r = redfish_request(host, "/redfish/v1", username, password)
        account_service_uri = r["AccountService"]["@odata.id"]
        redfish_request(host, account_service_uri, username, password)
        return True
    except Exception as e:
        logger.warning(f"Exception: {e}")
        return False


def get_obm_accounts(host: str, username: str, password: str) -> List[Dict]:
    """A vendor agnostic approach to crawling the API for OBM accounts"""
    try:
        # get account service
        r = redfish_request(host, "/redfish/v1", username, password)
        account_service_uri = r["AccountService"]["@odata.id"]
        logger.debug(f"account_service_url: {account_service_uri}")

        # get account collection uri
        r = redfish_request(host, account_service_uri, username, password)
        accounts_uri = r["Accounts"]["@odata.id"]
        logger.debug(f"accounts_url: {accounts_uri}")

        # get accounts
        r = redfish_request(host, accounts_uri, username, password)
        accounts = r["Members"]
        logger.debug(f"accounts: {accounts}")

        return accounts
    except Exception:
        logger.exception("Unable to fetch accounts from Redfish account service.")
        raise


def set_obm_creds(host: str, username: str, password: str, expected_username: str, expected_password: str) -> bool:
    """Find the account associated with the username in question"""
    try:
        accounts = get_obm_accounts(host, username, password)

        matched_account = None
        for account in accounts:
            account_url = account["@odata.id"]

            a = redfish_request(host, account_url, username, password)
            if expected_username == a["UserName"]:
                logger.debug(f"found account: {a}")
                matched_account = a
                break

        if not matched_account:
            raise Exception(f"Unable to find OBM account for {expected_username}")

        account_uri = matched_account["@odata.id"]

        payload = {"Password": expected_password}
        redfish_request(host, account_uri, username, password, "PATCH", payload)
        return True
    except Exception as e:
        logger.error(f"Exception: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__), description="Attempts to find the correct OBM credentials for a device"
    )
    parser.add_argument("--host", required=True, help="the address of the obm interface for the device")

    args = parser.parse_args()
    host = args.host
    expected_username = os.environ["OBM_USERNAME"]
    expected_password = os.environ["OBM_PASSWORD"]

    legacy_passwords = json.loads(os.getenv("OBM_LEGACY_PASSWORDS", "[]"))
    if not legacy_passwords:
        logger.info("env variable OBM_LEGACY_PASSWORDS was not set.")
        sys.exit(1)

    logger.info("Ensuring OBM credentials are synced correctly ...")

    if verify_auth(host, expected_username, expected_password):
        logger.info("OBM credentials are in sync.")
        sys.exit(0)
    else:
        logger.info("OBM credentials are NOT in sync. Trying known legacy/vendor credentials ...")

        # iDRAC defaults to blocking an IP address after 3 bad login attempts within 60 second. Since we have the
        # initial attempt above, we will sleep 35 seconds between any additional attempts.
        delay = 60
        username = os.getenv("OBM_LEGACY_USER", "root")
        for password in legacy_passwords:
            logger.info(f"Delaying for {delay} seconds to prevent failed auth lockouts ...")
            time.sleep(delay)
            if verify_auth(host, username, password):
                if set_obm_creds(host, username, password, expected_username, expected_password):
                    logger.info("OBM password has been synced.")
                    sys.exit(0)

    logger.info("Unable to sync the OBM password.")
    sys.exit(1)
