import base64
import subprocess
import sys

from understack_workflows import bmc_password_standard


def main():
    if len(sys.argv) != 2:
        print("Usage: bmc-kube-password <ip_addr>", file=sys.stderr)
        sys.exit(1)

    ip_addr = sys.argv[1]
    master_key = (
        subprocess.check_output(
            [
                "kubectl",
                "get",
                "secret",
                "-n",
                "argo-events",
                "bmc-master",
                "-o",
                "jsonpath={.data.key}",
            ]
        )
        .decode("utf-8")
        .strip()
    )
    master_key = base64.b64decode(master_key).decode("utf-8")
    if not master_key:
        print("Unable to obtain master secret", file=sys.stderr)
        sys.exit(2)

    print(
        bmc_password_standard.standard_password(ip_addr=ip_addr, master_key=master_key)
    )


if __name__ == "__main__":
    main()
