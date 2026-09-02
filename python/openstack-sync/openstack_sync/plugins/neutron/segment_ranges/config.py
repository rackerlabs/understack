"""Segment-range plugin constants.

Runtime configuration comes from
:class:`openstack_sync.hooks.framework.HookConfig`, built from the
``NEUTRON_SEGMENT_RANGE`` env prefix the Helm chart injects. The values here are
not configurable at runtime.
"""

from __future__ import annotations

#: Env prefix the Helm chart uses for this plugin's variables.
ENV_PREFIX = "NEUTRON_SEGMENT_RANGE"

#: shell-operator binding label for the CRD watch.
BINDING_NAME = "neutron-segment-ranges"

#: Network types Neutron binds to a physical network. VLAN and flat ranges
#: require ``physical_network``; the tunnelled types must omit it.
PHYSICAL_NETWORK_TYPES = frozenset({"vlan", "flat"})

#: Network types carried over a tunnel, which must not set ``physical_network``.
TUNNEL_NETWORK_TYPES = frozenset({"vxlan", "gre", "geneve"})
