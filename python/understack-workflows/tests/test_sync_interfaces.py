from unittest.mock import Mock

from understack_workflows import sync_interfaces


def test_sync_with_no_existing_interfaces(dell_nautobot_device):
    ironic_client = Mock()
    ironic_client.list_ports.return_value = []

    sync_interfaces.from_nautobot_to_ironic(
        pxe_interface="",
        nautobot_device=dell_nautobot_device,
        ironic_client=ironic_client,
    )

    assert ironic_client.create_port.call_count == 4

    ironic_client.create_port.assert_any_call(
        {
            "address": "14:23:f3:f5:25:f1",
            "uuid": "8c28941c-02cd-4aad-9e3f-93c39e08b58a",
            "node_uuid": "a3a2983f-d906-4663-943c-c41ab73c9b62",
            "name": f"{dell_nautobot_device.name}:NIC.Slot.1-2",
            "pxe_enabled": False,
            "local_link_connection": {
                "switch_id": "9c:54:16:f5:ad:27",
                "port_id": "Ethernet1/6",
                "switch_info": "f20-2-1.iad3.rackspace.net",
            },
            "physical_network": "F20-2[1-2]",
        }
    )

    ironic_client.create_port.assert_any_call(
        {
            "address": "d4:04:e6:4f:8d:b5",
            "uuid": "39d98f09-3199-40e0-87dc-e5ed6dce78e5",
            "node_uuid": "a3a2983f-d906-4663-943c-c41ab73c9b62",
            "name": f"{dell_nautobot_device.name}:NIC.Integrated.1-2",
            "pxe_enabled": False,
            "local_link_connection": {
                "switch_id": "9c:54:16:f5:ac:27",
                "port_id": "Ethernet1/5",
                "switch_info": "f20-2-2.iad3.rackspace.net",
            },
            "physical_network": "F20-2[1-2]",
        }
    )

    ironic_client.create_port.assert_any_call(
        {
            "address": "14:23:f3:f5:25:f0",
            "uuid": "7ac587c4-015b-4a0e-b579-91284cbd0406",
            "node_uuid": "a3a2983f-d906-4663-943c-c41ab73c9b62",
            "name": f"{dell_nautobot_device.name}:NIC.Slot.1-1",
            "pxe_enabled": False,
            "local_link_connection": {
                "switch_id": "9c:54:16:f5:ad:27",
                "port_id": "Ethernet1/6",
                "switch_info": "f20-2-2.iad3.rackspace.net",
            },
            "physical_network": "F20-2[1-2]",
        }
    )

    ironic_client.create_port.assert_any_call(
        {
            "address": "d4:04:e6:4f:8d:b4",
            "uuid": "ac2f1eae-188e-4fc6-9245-f9a6cf8b4ea8",
            "node_uuid": "a3a2983f-d906-4663-943c-c41ab73c9b62",
            "name": f"{dell_nautobot_device.name}:NIC.Integrated.1-1",
            "pxe_enabled": False,
            "local_link_connection": {
                "switch_id": "9c:54:16:f5:ab:27",
                "port_id": "Ethernet1/5",
                "switch_info": "f20-2-1.iad3.rackspace.net",
            },
            "physical_network": "F20-2[1-2]",
        }
    )
