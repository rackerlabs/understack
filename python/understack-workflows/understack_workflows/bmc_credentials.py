import base64
from time import sleep

from understack_workflows.bmc import AuthException
from understack_workflows.bmc import Bmc
from understack_workflows.helpers import setup_logger

FACTORY_B64 = b"Y2FsdmluLGNhbHZpbmNhbHZpbixjYWx2aW4xLGNhbHZpbmNhbHZpbjE="
_bstring = base64.b64decode(FACTORY_B64)
FACTORY_PASSWORDS = _bstring.decode("ascii").split(",")


logger = setup_logger(__name__)


def set_bmc_password(
    ip_address: str,
    new_password: str,
    username: str = "root",
    old_password: str | None = None,
):
    """Access BMC via redfish and change password from old password if needed.

    Old password, if not specified, is the maufacturer's factory default.

    Check that we can log in using the standard password.

    If that doesn't work, try the old password, if that succeeds then we change
    the BMC password to our standard one.

    Once the password has been changed, we check that it works by logging in
    again, otherwise raise an Exception.
    """
    bmc = Bmc(ip_address=ip_address, username=username, password=new_password)

    token, session = bmc.get_session(new_password)
    if token and session:
        logger.info("Production BMC credentials are working on this BMC.")
        bmc.close_session(session=session, token=token)
        return

    logger.info(
        "Production BMC credentials don't work on this BMC. "
        "Trying old / factory default credentials."
    )

    for test_password in filter(None, [old_password, *FACTORY_PASSWORDS]):
        token, session = bmc.get_session(test_password)
        if token and session:
            break
        # Go Slow, or else the BMC will lock us out for a
        # few mins if we try too may "incorrect passwords"
        sleep(30)
    if not token:
        raise AuthException(
            f"Unable to log in to BMC {ip_address} with any known password!"
        )
    if token and session:
        logger.info("Changing BMC password to standard")
        bmc.set_bmc_creds(password=new_password, token=token)
        logger.info("BMC password has been set.")
        bmc.close_session(session=session, token=token)

    token, session = bmc.get_session(new_password)
    if token and session:
        logger.info("Production BMC credentials are working on this BMC.")
        bmc.close_session(session=session, token=token)
