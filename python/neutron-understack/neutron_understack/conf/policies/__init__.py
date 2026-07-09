import itertools

from neutron_understack.conf.policies import evpn


def list_rules():
    return itertools.chain(
        evpn.list_rules(),
    )
