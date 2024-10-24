import os
import sys

from understack_workflows.bmc_password_standard import standard_password


def main(program_name, bmc_ip_address=None):
    """CLI script to obtain standard BMC Password.

    Requires the master secret to be available in BMC_MASTER environment
    variable.
    """
    if bmc_ip_address is None:
        print(f"Usage: {program_name} <BMC IP Address>", file=sys.stderr)
        exit(1)

    if os.getenv("BMC_MASTER") is None:
        print("Please set the BMC_MASTER environment variable")
        exit(1)

    password = standard_password(bmc_ip_address, os.getenv("BMC_MASTER"))
    print(password)


main(*sys.argv)
