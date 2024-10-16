import sys

from understack_workflows.bmc_password_standard import standard_password
from understack_workflows.helpers import credential


def main(program_name, bmc_ip_address=None):
    """CLI script to obtain standard BMC Password.

    Requires the master secret to be available in /etc/bmc_master/key
    """
    if bmc_ip_address is None:
        print(f"Usage: {program_name} <BMC IP Address>", file=sys.stderr)
        exit(1)

    master_secret = credential("bmc_master", "key")
    print(standard_password(bmc_ip_address, master_secret))


main(*sys.argv)
