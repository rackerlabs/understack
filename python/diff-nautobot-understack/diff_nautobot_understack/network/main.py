from pprint import pprint
from diffsync.enum import DiffSyncFlags
from diff_nautobot_understack.network.adapters.openstack_network import (
    Network as OpenstackNetwork,
)
from diff_nautobot_understack.network.adapters.ucvni import Network as UcvniNetwork


def openstack_network_diff_from_ucvni_network():
    openstack_network = OpenstackNetwork()
    openstack_network.load()

    ucvni_network = UcvniNetwork()
    ucvni_network.load()
    openstack_network_destination_ucvni_source = openstack_network.diff_from(
        ucvni_network, flags=DiffSyncFlags.CONTINUE_ON_FAILURE
    )
    pprint(" Nautobot ucvnis ⟹ Openstack networks ")
    summary = openstack_network_destination_ucvni_source.summary()
    pprint(summary, width=120)
    pprint(openstack_network_destination_ucvni_source.dict(), width=120)
