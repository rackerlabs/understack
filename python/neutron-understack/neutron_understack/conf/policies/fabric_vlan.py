from neutron.conf.policies import base
from oslo_policy import policy

COLLECTION_PATH = "/networks"
RESOURCE_PATH = "/networks/{id}"

ACTION_POST = [
    {"method": "POST", "path": COLLECTION_PATH},
]
ACTION_PUT = [
    {"method": "PUT", "path": RESOURCE_PATH},
]
ACTION_GET = [
    {"method": "GET", "path": COLLECTION_PATH},
    {"method": "GET", "path": RESOURCE_PATH},
]

rules = [
    policy.DocumentedRuleDefault(
        name="create_network:fabric_vlan",
        check_str=base.ADMIN_OR_PROJECT_MEMBER,
        scope_types=["project"],
        description="Specify ``fabric_vlan`` attribute when creating a network",
        operations=ACTION_POST,
    ),
    policy.DocumentedRuleDefault(
        name="update_network:fabric_vlan",
        check_str=base.ADMIN_OR_PROJECT_MEMBER,
        scope_types=["project"],
        description="Specify ``fabric_vlan`` attribute when updating a network",
        operations=ACTION_PUT,
    ),
    policy.DocumentedRuleDefault(
        name="get_network:fabric_vlan",
        check_str=base.ADMIN_OR_PROJECT_READER,
        scope_types=["project"],
        description="Get ``fabric_vlan`` attribute of a network",
        operations=ACTION_GET,
    ),
]


def list_rules():
    return rules
