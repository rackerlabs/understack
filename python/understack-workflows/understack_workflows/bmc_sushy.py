from sushy import Sushy

from understack_workflows.bmc_password_standard import standard_password
from understack_workflows.helpers import credential


def bmc_sushy_session(ip_addr, username = "root", password = None):
    url = f"https://{ip_addr}"

    if password is None:
        master_secret = credential("bmc_master", "key")
        password = standard_password(ip_addr, master_secret)

    return Sushy(url, username=username, password=password, verify=False)
