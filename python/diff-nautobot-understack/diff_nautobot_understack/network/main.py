from diffsync.diff import Diff
from diffsync.enum import DiffSyncFlags
from diff_nautobot_understack.network.adapters.openstack_network import (
    Network as OpenstackNetwork,
)
from diff_nautobot_understack.network.adapters.ucvni import Network as UcvniNetwork


def openstack_network_diff_from_ucvni_network() -> Diff:
    openstack_network = OpenstackNetwork()
    openstack_network.load()

    ucvni_network = UcvniNetwork()
    ucvni_network.load()
    openstack_network_destination_ucvni_source = openstack_network.diff_from(
        ucvni_network, flags=DiffSyncFlags.CONTINUE_ON_FAILURE
    )
    return openstack_network_destination_ucvni_source
