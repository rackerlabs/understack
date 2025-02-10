import requests
import urllib3

from understack_workflows.helpers import setup_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # type: ignore

FACTORY_PASSWORD = "calvin"  # noqa: S105 we know this is hardcoded

logger = setup_logger(__name__)


def set_bmc_password(ip_address, new_password, username="root", old_password=None):
    """Access BMC via redfish and change password from old password if needed.

    Old password, if not specified, is the maufacturer's factory default.

    Check that we can log in using the standard password.

    If that doesn't work, try the old password, if that succeeds then we change
    the BMC password to our standard one.

    Once the password has been changed, we check that it works by logging in
    again, otherwise raise an Exception.
    """
    if not old_password:
        old_password = FACTORY_PASSWORD

    token, session = _verify_auth(ip_address, username, new_password)
    if token:
        logger.info("Production BMC credentials are working on this BMC.")
        close_session(ip_address, token, session)
        return

    logger.info(
        "Production BMC credentials don't work on this BMC. "
        "Trying old / factory default credentials."
    )
    token, session = _verify_auth(ip_address, username, old_password)
    if not token:
        raise Exception(
            f"Unable to log in to BMC {ip_address} with any known password!"
        )

    logger.info("Changing BMC password to standard")
    _set_bmc_creds(ip_address, token, username, new_password)
    logger.info("BMC password has been set.")
    close_session(ip_address, token, session)

    token = _verify_auth(ip_address, username, new_password)
    if token:
        logger.info("Production BMC credentials are working on this BMC.")
        close_session(ip_address, token, session)


def _verify_auth(
    host: str, username: str = "root", password: str = ""
) -> tuple[str | None, str | None]:
    """Test whether provided credentials work against a secured API endpoint.

    Returns authentication token and session path on success
    Returns None, None on authorisation failure
    Raises an Exception for other kinds of errors (e.g. timeout, etc)
    """
    try:
        response = requests.request(
            method="POST",
            url=f"https://{host}/redfish/v1/SessionService/Sessions",
            verify=False,
            timeout=30,
            json={"UserName": username, "Password": password},
        )
        if response.status_code == 401:
            return None, None
        if response.status_code >= 400:
            raise Exception(
                f"BMC {host} password login failed: "
                f" {response.status_code} {response.json()}"
            )
        return response.headers["X-Auth-Token"], response.json()["@odata.id"]
    except Exception as e:
        raise e from None


def close_session(host, token, session):
    _redfish_request(host, session, token, "DELETE")


def _get_bmc_accounts(host: str, token: str, username: str) -> list[dict]:
    """A vendor agnostic approach to crawling the API for BMC accounts."""
    try:
        # get account service
        r = _redfish_request(host, "/redfish/v1", token)
        account_service_uri = r["AccountService"]["@odata.id"]
        logger.debug("account_service_url: %s", account_service_uri)

        # get account collection uri
        r = _redfish_request(host, account_service_uri, token)
        accounts_uri = r["Accounts"]["@odata.id"]
        logger.debug("accounts_url: %s", accounts_uri)

        # get accounts
        r = _redfish_request(host, accounts_uri, token)
        accounts = r["Members"]
        logger.debug("accounts: %s", accounts)

        return accounts
    except Exception:
        logger.exception("Can't fetch accounts from Redfish account service.")
        raise


def _set_bmc_creds(host: str, token: str, username: str, new_password: str):
    """Change password for the account associated with username in question."""
    accounts = _get_bmc_accounts(host, token, username)

    matched_account = None
    for account in accounts:
        account_url = account["@odata.id"]

        a = _redfish_request(host, account_url, token)
        if username == a["UserName"]:
            logger.debug("found account: %s", a)
            matched_account = a
            break

    if not matched_account:
        raise Exception(f"Unable to find BMC account for {username}")

    account_uri = matched_account["@odata.id"]

    payload = {"Password": new_password}
    _redfish_request(host, account_uri, token, "PATCH", payload)


def _redfish_request(
    host: str, uri: str, token: str, method: str = "GET", payload: dict | None = None
) -> dict:
    url = f"https://{host}{uri}"
    headers = {"X-Auth-Token": token}
    try:
        response = requests.request(
            method, url, verify=False, timeout=15, json=payload, headers=headers
        )
        if response.status_code >= 400:
            raise Exception(
                f"Redfish HTTP {response.status_code} " f"from {uri}: {response.text}"
            )

        else:
            return response.json()
    except Exception as e:
        raise e from None
