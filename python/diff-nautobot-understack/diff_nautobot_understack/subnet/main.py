from diffsync.diff import Diff
from diffsync.enum import DiffSyncFlags

from diff_nautobot_understack.subnet.adapters.nautobot_prefix import Prefixes
from diff_nautobot_understack.subnet.adapters.openstack_subnet import Subnets


def openstack_subnets_diff_from_nautobot_prefixes() -> Diff:
    """Compare all OpenStack subnets with Nautobot prefixes."""
    openstack_subnets = Subnets()
    openstack_subnets.load()

    nautobot_prefixes = Prefixes()
    nautobot_prefixes.load()

    return nautobot_prefixes.diff_from(
        openstack_subnets, flags=DiffSyncFlags.CONTINUE_ON_FAILURE
    )
