import logging
import os
import sys
from base64 import b64encode

from understack_workflows.argo_workflow import create_secret
from understack_workflows.bmc_password_standard import standard_password

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def base64(string):
    return b64encode(string.encode()).decode()


def require_environment_variables(*names):
    missing_environment_variables = [name for name in names if os.getenv(name) is None]
    if missing_environment_variables:
        print(f"Please set environment: {missing_environment_variables=}")
        exit(1)


def _create_secret(data):
    return create_secret(
        namespace=os.getenv("WF_NS"),
        workflow_name=os.getenv("WF_NAME"),
        owner_uid=os.getenv("WF_UID"),
        name=f"creds-bmc-{os.getenv('WF_UID')}",
        data=data,
    )


def main(program_name, ip_address=None):
    """This is intended for use by an Argo Workflow.

    It will generate BMC credentials for the given BMC IP address.

    It creates a new kubernetes secret containing the username and password.

    The name of the secret is returned.
    """
    if ip_address is None:
        print(f"Usage: {program_name} <BMC IP Address>", file=sys.stderr)
        exit(1)

    require_environment_variables("BMC_MASTER", "WF_NS", "WF_NAME", "WF_UID")

    username = "root"
    password = standard_password(ip_address, os.getenv("BMC_MASTER"))

    data = {
        "username": base64(username),
        "password": base64(password),
    }

    secret_name = _create_secret(data)

    with open("/tmp/output.txt", "w") as f:
        f.write(secret_name)


main(*sys.argv)
