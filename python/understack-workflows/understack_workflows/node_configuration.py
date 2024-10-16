from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field

from ironicclient.v1.node import Node

from understack_workflows.bmc_password_standard import standard_password
from understack_workflows.helpers import credential
from understack_workflows.redfish_driver_info import RedfishDriverInfo


def dict_without_none(data):
    return {k: v for k, v in data if v is not None}


@dataclass
class IronicNodeConfiguration:
    """The boot interface for a Node, e.g. “pxe”."""

    uuid: str
    """The UUID for the resource."""

    name: str
    """Human-readable identifier for the Node resource. May be undefined.
    Certain words are reserved."""

    driver: str
    """The name of the driver used to manage this Node."""

    driver_info: RedfishDriverInfo = field(default_factory=RedfishDriverInfo)
    """All the metadata required by the driver to manage this Node. List of
    fields varies between drivers, and can be retrieved from the
    /v1/drivers/<DRIVER_NAME>/properties resource."""

    boot_interface: str | None = None

    conductor_group: str | None = None
    """The conductor group for a node. Case-insensitive str up to 255
    characters, containing a-z, 0-9, _, -, and .."""

    console_interface: str | None = None
    """The console interface for a node, e.g. “no-console”."""

    deploy_interface: str | None = None
    """The deploy interface for a node, e.g. “iscsi”."""

    extra: dict = field(default_factory=dict)
    """A set of one or more arbitrary metadata key and value pairs."""

    inspect_interface: str | None = None
    """The interface used for node inspection, e.g. “no-inspect”."""

    management_interface: str | None = None
    """Interface for out-of-band node management, e.g. “ipmitool”."""

    network_interface: str | None = None
    """Which Network Interface provider to use when plumbing the network
    connections for this Node."""

    power_interface: str | None = None
    """Interface used for performing power actions on the node, e.g.
    “ipmitool”."""

    properties: dict = field(default_factory=dict)
    """Physical characteristics of this Node. Populated during inspection, if
    performed. Can be edited via the REST API at any time."""

    raid_interface: str | None = None
    """Interface used for configuring RAID on this node, e.g. “no-raid”."""

    rescue_interface: str | None = None
    """The interface used for node rescue, e.g. “no-rescue”."""

    resource_class: str = ""
    """A str which can be used by external schedulers to identify this Node as
    a unit of a specific type of resource."""

    storage_interface: str | None = None
    """Interface used for attaching and detaching volumes on this node, e.g.
    “cinder”."""

    vendor_interface: str | None = None
    """Interface for vendor-specific functionality on this node, e.g.
    “no-vendor”."""

    owner: str = ""
    """A str or UUID of the tenant who owns the object."""

    description: str = ""
    """Informational text about this node."""

    lessee: str = ""
    """A str or UUID of the tenant who is leasing the object."""

    shard: str = ""
    """A str indicating the shard this node belongs to."""

    automated_clean: bool = False
    """Indicates whether the node will perform automated clean or not."""

    bios_interface: str | None = None
    """The bios interface to be used for this node."""

    chassis_uuid: str | None = ""
    """UUID of the chassis associated with this Node. May be empty or None."""

    instance_info: dict = field(default_factory=dict)
    """Information used to customize the deployed image. May include root
    partition size, a base 64 encoded config drive, and other metadata. Note
    that this field is erased automatically when the instance is deleted (this
    is done by requesting the Node provision state be changed to DELETED)."""

    instance_uuid: str = ""
    """UUID of the Nova instance associated with this Node."""

    maintenance: bool = False
    """Whether or not this Node is currently in “maintenance mode”. Setting a
    Node into maintenance mode removes it from the available resource pool and
    halts some internal automation. This can happen manually (eg, via an API
    request) or automatically when Ironic detects a hardware fault that
    prevents communication with the machine."""

    maintenance_reason: str = ""
    """User-settable description of the reason why this Node was placed into
    maintenance mode"""

    network_data: dict = field(default_factory=dict)
    """Static network configuration in the OpenStack network data format to use
    during deployment and cleaning. Requires a specially crafted ramdisk, see
    DHCP-less documentation."""

    parent_node: str = ""
    """An optional UUID which can be used to denote the “parent” baremetal
    node."""

    protected: bool = False
    """Whether the node is protected from undeploying, rebuilding and
    deletion."""

    protected_reason: str = ""
    """The reason the node is marked as protected."""

    retired: bool = False
    """Whether the node is retired and can hence no longer be provided, i.e.
    move from manageable to available, and will end up in manageable after
    cleaning (rather than available)."""

    retired_reason: str = ""
    """The reason the node is marked as retired."""

    CREATE_EXCLUDED_KEYWORDS = [
        "owner",
        "description",
        "lessee",
        "shard",
        "instance_info",
        "instance_uuid",
        "maintenance",
        "maintenance_reason",
        "protected",
        "protected_reason",
        "retired",
        "retired_reason",
        "parent_node",
    ]

    def create_node(self, client) -> Node:
        """Create a node from our config."""
        # this follows the code in the python-ironicclient
        field_list = ["uuid", "name", "driver", "driver_info"]
        fields = dict(
            (k, v)
            for (k, v) in asdict(self, dict_factory=dict_without_none).items()
            if k in field_list and v is not None
        )
        return client.create_node(fields)

    @staticmethod
    def from_event(event: dict) -> IronicNodeConfiguration:
        """Create an instance from Nautobot webhook event data.

        Here we consume the event that Nautobot publishes whenever an ethernet
        interface is updated.  (Other types of event will raise an error)

        The IronicNodeConfiguration is populated with minimal amount of
        information, including id, name and BMC driver information.
        """
        model = event.get("model")
        if model not in ["interface"]:
            raise ValueError(f"'{model}' events not supported")

        data = event["data"]

        # if we got an iDRAC interface then we'll want to use
        # the idrac driver otherwise redfish
        driver = "idrac" if data["name"] == "iDRAC" else "redfish"

        bmc_master_key = credential("bmc_master", "key")
        bmc_ip_address = data["ip_addresses"][0]["host"]
        bmc_username = "root"
        bmc_password = standard_password(bmc_ip_address, bmc_master_key)

        di = RedfishDriverInfo(
            redfish_address=f"https://{bmc_ip_address}",
            redfish_verify_ca=False,
            redfish_username=bmc_username,
            redfish_password=bmc_password,
        )

        return IronicNodeConfiguration(
            data["device"]["id"],
            data["device"]["name"],
            driver,
            driver_info=di,
        )
