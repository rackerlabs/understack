"""Router-flavor plugin constants.

Runtime configuration comes from :class:`openstack_sync.hooks.framework.HookConfig`,
built from the ``NEUTRON_ROUTER_FLAVOR`` env prefix the Helm chart injects. The
values here are not configurable at runtime: the chart never set them, so
carrying env plumbing for them only obscured what they are.
"""

from __future__ import annotations

#: Env prefix the Helm chart uses for this plugin's variables.
ENV_PREFIX = "NEUTRON_ROUTER_FLAVOR"

#: shell-operator binding label for the CRD watch.
BINDING_NAME = "neutron-router-flavors"

#: The only service type Neutron accepts for router flavors
#: (``plugin_constants.L3`` in neutron-lib). The CRD pins it with an enum.
SERVICE_TYPE = "L3_ROUTER_NAT"
