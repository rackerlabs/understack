import itertools

from neutron_understack.conf.policies import evpn
from neutron_understack.conf.policies import fabric_vlan


def list_rules():
    return itertools.chain(
        evpn.list_rules(),
        fabric_vlan.list_rules(),
    )
