from dataclasses import dataclass
from unittest.mock import Mock

from understack_workflows import sync_interfaces
from understack_workflows.bmc_chassis_info import InterfaceInfo


@dataclass
class MockIronicNode:
    name: str
    uuid: str


def test_sync_with_no_existing_interfaces():
    device_name = "Dell-ABC123"

    ironic_node = MockIronicNode(
        uuid="a3a2983f-d906-4663-943c-c41ab73c9b62",
        name=device_name,
    )
    ironic_client = Mock()
    ironic_client.list_ports.return_value = []

    print(f"NAME {ironic_node.name=}")

    discovered_interfaces = [
        InterfaceInfo(
            name="NIC.Slot.1-1",
            description="",
            mac_address="14:23:f3:f5:25:f1",
            remote_switch_mac_address="c4:7e:e0:e4:10:7f",
            remote_switch_port_name="Ethernet1/6",
            remote_switch_data_stale=False,
        ),
        InterfaceInfo(
            name="NIC.Integrated.1-2",
            description="",
            mac_address="14:23:f3:f5:25:f2",
            remote_switch_mac_address="c4:7e:e0:e4:32:df",
            remote_switch_port_name="Ethernet1/6",
            remote_switch_data_stale=False,
        ),
    ]

    sync_interfaces.update_ironic_baremetal_ports(
        ironic_node=ironic_node,
        discovered_interfaces=discovered_interfaces,
        pxe_interface_name="",
        ironic_client=ironic_client,
    )

    assert ironic_client.create_port.call_count == 2

    ironic_client.create_port.assert_any_call(
        {
            "address": "14:23:f3:f5:25:f1",
            "node_uuid": "a3a2983f-d906-4663-943c-c41ab73c9b62",
            "name": "Dell-ABC123:NIC.Slot.1-1",
            "pxe_enabled": False,
            "local_link_connection": {
                "switch_id": "c4:7e:e0:e4:10:7f",
                "port_id": "Ethernet1/6",
                "switch_info": "f20-2-1.iad3.rackspace.net",
            },
            "physical_network": "f20-2-network",
        }
    )

    ironic_client.create_port.assert_any_call(
        {
            "address": "14:23:f3:f5:25:f2",
            "node_uuid": "a3a2983f-d906-4663-943c-c41ab73c9b62",
            "name": "Dell-ABC123:NIC.Integrated.1-2",
            "pxe_enabled": False,
            "local_link_connection": {
                "switch_id": "c4:7e:e0:e4:32:df",
                "port_id": "Ethernet1/6",
                "switch_info": "f20-2-2.iad3.rackspace.net",
            },
            "physical_network": "f20-2-network",
        }
    )
