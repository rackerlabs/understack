from diffsync.diff import Diff
from diffsync.enum import DiffSyncFlags
from rich import print

from diff_nautobot_understack.network.adapters.openstack_network import (
    Network as OpenstackNetwork,
)
from diff_nautobot_understack.network.adapters.ucvni import Network as UcvniNetwork


def openstack_network_diff_from_ucvni_network() -> Diff:
    openstack_network = OpenstackNetwork()
    try:
        openstack_network.load()
    except Exception:
        print("Error retrieving networks from Openstack")
    ucvni_network = UcvniNetwork()
    try:
        ucvni_network.load()
    except Exception:
        print("Error retrieving ucvnis from Nautobot")
    openstack_network_destination_ucvni_source = openstack_network.diff_from(
        ucvni_network, flags=DiffSyncFlags.CONTINUE_ON_FAILURE
    )
    return openstack_network_destination_ucvni_source
