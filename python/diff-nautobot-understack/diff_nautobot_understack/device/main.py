from diffsync.diff import Diff
from diffsync.enum import DiffSyncFlags

from diff_nautobot_understack.device.adapters.ironic_node import Nodes
from diff_nautobot_understack.device.adapters.nautobot_device import Devices


def ironic_nodes_diff_from_nautobot_devices() -> Diff:
    """Compare all Ironic nodes with Nautobot devices."""
    ironic_nodes = Nodes()
    ironic_nodes.load()

    nautobot_devices = Devices()
    nautobot_devices.load()

    return nautobot_devices.diff_from(
        ironic_nodes, flags=DiffSyncFlags.CONTINUE_ON_FAILURE
    )
