import base64
import logging
from time import sleep

from understack_workflows.bmc import AuthException
from understack_workflows.bmc import Bmc
from understack_workflows.bmc import RedfishRequestError

# Factory-default root passwords for various BMCs, most likely first
FACTORY_B64 = b"Y2FsdmluLGNhbHZpbmNhbHZpbixjYWx2aW4xLGNhbHZpbmNhbHZpbjE="
FACTORY_PASSWORDS = base64.b64decode(FACTORY_B64).decode("ascii").split(",")


logger = logging.getLogger(__name__)


def set_bmc_password(
    ip_address: str,
    new_password: str,
    username: str = "root",
    old_password: str | None = None,
):
    """Access BMC via redfish and change password from old password if needed.

    Check that we can log in using the standard password.

    If the standard password is not working, log in and CHANGE the BMC password
    to our standard one.

    We attempt old_password, and if that is not supplied or doesn't work, try
    some well-known maufacturers' factory defaults.

    If all the above cannot be completed we raise an Exception.  Therefore if
    this function returns, the production password is working.
    """
    bmc = Bmc(ip_address=ip_address, username=username)

    candidate_passwords = _remove_dups_and_nulls(
        new_password, old_password, *FACTORY_PASSWORDS
    )

    failures = []
    for attempt, password in enumerate(candidate_passwords):
        if attempt > 1:
            logger.debug(
                "Waiting for 1 minute before BMC login attempt "
                "with password %s of %s to avoid security lock-out",
                attempt + 1,
                len(candidate_passwords),
            )
            sleep(60)

        try:
            return _log_in_and_set_password(bmc, password, new_password)
        except RedfishRequestError as e:
            failures.append(e)

    raise AuthException(
        f"Unable to log in to BMC {ip_address} with any known password! "
        f"Errors from all {len(failures)} attempts: {failures}"
    )


def _log_in_and_set_password(bmc, password, new_password):
    if password != new_password:
        with bmc.session(password) as token:
            logger.info(
                "Login successful using old/default password. "
                "Changing BMC password to production standard."
            )
            bmc.set_bmc_creds(password=new_password, token=token)
            logger.info("BMC password has been set.")

    with bmc.session(new_password):
        logger.info("Production BMC credentials are working on this BMC.")


def _remove_dups_and_nulls(*args):
    result = []
    for x in args:
        if x and x not in result:
            result.append(x)
    return result
