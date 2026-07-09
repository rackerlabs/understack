from neutron_lib import constants
from neutron_lib.api import converters
from neutron_lib.api.definitions import l3

ALIAS = "understack_vni"
IS_SHIM_EXTENSION = False
IS_STANDARD_ATTR_EXTENSION = False
NAME = "Understack Router VNI"
API_PREFIX = ""
DESCRIPTION = "Router extension for Understack hardware VRF VNI allocation"
UPDATED_TIMESTAMP = "2026-07-01T00:00:00-00:00"
RESOURCE_NAME = l3.ROUTER
COLLECTION_NAME = l3.ROUTERS

EVPN_VNI = "evpn_vni"

RESOURCE_ATTRIBUTE_MAP = {
    COLLECTION_NAME: {
        EVPN_VNI: {
            "allow_post": True,
            "allow_put": False,
            "convert_to": converters.convert_to_int_if_not_none,
            "default": 0,
            "is_visible": True,
            "is_filter": True,
            "is_sort_key": True,
            "enforce_policy": True,
            "validate": {"type:range_or_none": [0, constants.MAX_VXLAN_VNI]},
        },
    },
}

SUB_RESOURCE_ATTRIBUTE_MAP = {}
ACTION_MAP = {}
REQUIRED_EXTENSIONS = [l3.ALIAS]
OPTIONAL_EXTENSIONS = []
ACTION_STATUS = {}
