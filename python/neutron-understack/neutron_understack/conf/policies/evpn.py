from neutron.conf.policies import base
from oslo_policy import policy

from neutron_understack import evpn_compat

COLLECTION_PATH = "/routers"
RESOURCE_PATH = "/routers/{id}"

ACTION_POST = [
    {"method": "POST", "path": COLLECTION_PATH},
]
ACTION_GET = [
    {"method": "GET", "path": COLLECTION_PATH},
    {"method": "GET", "path": RESOURCE_PATH},
]

rules = [
    policy.DocumentedRuleDefault(
        name="create_router:evpn_vni",
        check_str=base.ADMIN,
        scope_types=["project"],
        description="Specify ``evpn_vni`` attribute when creating a router",
        operations=ACTION_POST,
    ),
    policy.DocumentedRuleDefault(
        name="get_router:evpn_vni",
        check_str=base.ADMIN_OR_PROJECT_READER,
        scope_types=["project"],
        description="Get ``evpn_vni`` attribute of a router",
        operations=ACTION_GET,
    ),
]


def list_rules():
    # When core owns EVPN it registers these same policies; registering them
    # again makes neutron.policy.register_rules() raise DuplicatePolicyError
    # and abort policy initialization for the whole neutron-server.
    if evpn_compat.core_provides_evpn():
        return []
    return rules
