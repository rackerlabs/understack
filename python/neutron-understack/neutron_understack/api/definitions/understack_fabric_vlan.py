from neutron_lib import constants
from neutron_lib.api import converters
from neutron_lib.api.definitions import network

ALIAS = "understack_fabric_vlan"
IS_SHIM_EXTENSION = False
IS_STANDARD_ATTR_EXTENSION = False
NAME = "Understack Network Fabric VLAN"
API_PREFIX = ""
DESCRIPTION = "Network extension pinning a network to one fabric-wide VLAN"
UPDATED_TIMESTAMP = "2026-11-05T00:00:00-00:00"
RESOURCE_NAME = network.RESOURCE_NAME
COLLECTION_NAME = network.COLLECTION_NAME

FABRIC_VLAN = "fabric_vlan"

RESOURCE_ATTRIBUTE_MAP = {
    COLLECTION_NAME: {
        FABRIC_VLAN: {
            "allow_post": True,
            "allow_put": True,
            "convert_to": converters.convert_to_int_if_not_none,
            "default": constants.ATTR_NOT_SPECIFIED,
            "is_visible": True,
            "is_filter": True,
            "is_sort_key": True,
            "enforce_policy": True,
            "validate": {
                "type:range_or_none": [constants.MIN_VLAN_TAG, constants.MAX_VLAN_TAG]
            },
        },
    },
}

SUB_RESOURCE_ATTRIBUTE_MAP = {}
ACTION_MAP = {}
REQUIRED_EXTENSIONS = []
OPTIONAL_EXTENSIONS = []
ACTION_STATUS = {}
