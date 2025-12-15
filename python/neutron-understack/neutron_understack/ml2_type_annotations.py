from typing import Any
from typing import Literal
from typing import NotRequired
from typing import TypedDict

NetworkTypeName = Literal["vxlan", "vlan"]
PortStatusName = Literal["DOWN", "ACTIVE"]


class NetworkSegmentDict(TypedDict):
    id: str
    network_id: str
    network_type: NetworkTypeName
    physical_network: str | None
    segmentation_id: int


ShortNetworkSegmentDict = TypedDict(
    "ShortNetworkSegmentDict",
    {
        "provider:network_type": NetworkTypeName,
        "provider:physical_network": str | None,
        "provider:segmentation_id": int,
    },
)

NetworkDict = TypedDict(
    "NetworkDict",
    {
        "admin_state_up": bool,
        "availability_zone_hints": list,
        "availability_zones": list,
        "created_at": str,
        "description": str,
        "id": str,
        "ipv4_address_scope": Any,
        "ipv6_address_scope": Any,
        "l2_adjacency": bool,
        "mtu": int,
        "name": str,
        "project_id": str,
        "provider:network_type": NotRequired[NetworkTypeName | None],
        "provider:physical_network": NotRequired[str | None],
        "provider:segmentation_id": NotRequired[int | None],
        "revision_number": int,
        "router:external": bool,
        "segments": NotRequired[list[ShortNetworkSegmentDict]],
        "shared": bool,
        "standard_attr_id": int,
        "status": str,
        "subnets": list,
        "tags": list[str],
        "tenant_id": str,
        "updated_at": str,
        "vlan_transparent": Any,
    },
)


class FixedIpsDict(TypedDict):
    subnet_id: str
    ip_address: str


PortDict = TypedDict(
    "PortDict",
    {
        "id": str,
        "name": str,
        "network_id": str,
        "tenant_id": str,
        "mac_address": str,
        "admin_state_up": bool,
        "status": PortStatusName,
        "device_id": str,
        "device_owner": str,
        "standard_attr_id": int,
        "fixed_ips": list[FixedIpsDict],
        "project_id": str,
        "security_groups": list[str],
        "binding:vnic_type": str,
        "binding:profile": dict,
        "binding:host_id": str,
        "binding:vif_type": str,
        "binding:vif_details": dict,
        "allowed_address_pairs": list,
        "extra_dhcp_opts": list,
        "description": str,
        "ip_allocation": str,
        "tags": list,
        "created_at": str,
        "updated_at": str,
        "revision_number": int,
        "network": NotRequired[NetworkDict],
    },
)

example_network: NetworkDict = {
    "id": "c57e4a02-73bb-4c6e-ab03-537ea11168e3",
    "name": "provisioning",
    "tenant_id": "32e02632f4f04415bab5895d1e7247b7",
    "admin_state_up": True,
    "mtu": 1500,
    "status": "ACTIVE",
    "subnets": ["b0fa63d0-fb0c-446f-bfd3-26c0a50730c0"],
    "standard_attr_id": 22,
    "shared": False,
    "availability_zone_hints": [],
    "availability_zones": [],
    "ipv4_address_scope": None,
    "ipv6_address_scope": None,
    "router:external": False,
    "vlan_transparent": None,
    "description": "",
    "l2_adjacency": True,
    "tags": [],
    "created_at": "2024-09-19T20:55:45Z",
    "updated_at": "2024-09-24T15:49:54Z",
    "revision_number": 6,
    "project_id": "32e02632f4f04415bab5895d1e7247b7",
    "provider:network_type": "vxlan",
    "provider:physical_network": None,
    "provider:segmentation_id": 4010,
}


class NetworkContext:
    current: NetworkDict
    original: NetworkDict
    network_segments: list[NetworkSegmentDict]


class PortContext:
    current: PortDict
    original: PortDict
    network: NetworkContext
    status: str
    original_status: str
    plugin_context: Any
    _plugin_context: Any
    _plugin: Any
    vif_type: str
    original_vif_type: str

    binding_levels: Any
    original_binding_levels: Any
    top_bound_segment: Any
    original_top_bound_segment: Any
    bottom_bound_segment: Any
    original_bottom_bound_segment: Any
    host: Any
    original_host: Any
    vif_details: Any
    original_vif_details: Any
    segments_to_bind: Any

    def set_binding(
        self, segment_id: str, vif_type: str, vif_details: dict, status: str
    ) -> None: ...

    def allocate_dynamic_segment(self, segment: dict) -> dict: ...

    def release_dynamic_segment(self, segment_id: str) -> dict: ...


class BindingLevelsDict(TypedDict):
    bound_driver: Literal["understack"]
    bound_segment: NetworkSegmentDict
