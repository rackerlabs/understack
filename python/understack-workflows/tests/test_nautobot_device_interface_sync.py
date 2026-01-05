"""Tests for nautobot_device_interface_sync module."""

import uuid
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    EXIT_STATUS_FAILURE,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    EXIT_STATUS_SUCCESS,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import InterfaceInfo
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    _assign_ip_to_interface,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    _build_interface_map_from_inventory,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    _build_interfaces_from_ports,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    _cleanup_stale_interfaces,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    _create_nautobot_interface,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    _delete_nautobot_interface,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    _extract_node_uuid_from_event,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    _get_interface_description,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    _get_interface_type,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    _handle_cable_management,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    _update_nautobot_interface,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    handle_interface_sync_event,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    sync_idrac_interface,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    sync_interfaces_from_data,
)
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    sync_interfaces_to_nautobot,
)


class TestGetInterfaceType:
    """Test cases for _get_interface_type function."""

    def test_slot_interface(self):
        assert _get_interface_type("NIC.Slot.1-1") == "25gbase-x-sfp28"

    def test_embedded_interface(self):
        assert _get_interface_type("NIC.Embedded.1-1-1") == "25gbase-x-sfp28"

    def test_integrated_interface(self):
        assert _get_interface_type("NIC.Integrated.1-1") == "25gbase-x-sfp28"

    def test_unknown_interface(self):
        assert _get_interface_type("eth0") == "unknown"


class TestGetInterfaceDescription:
    """Test cases for _get_interface_description function."""

    def test_embedded_nic_description(self):
        result = _get_interface_description("NIC.Embedded.1-1-1")
        assert result == "Embedded NIC 1 Port 1 Partition 1"

    def test_embedded_nic_two_parts(self):
        result = _get_interface_description("NIC.Embedded.2-1")
        assert result == "Embedded NIC 2 Port 1"

    def test_integrated_nic_description(self):
        result = _get_interface_description("NIC.Integrated.1-2")
        assert result == "Integrated NIC 1 Port 2"

    def test_slot_nic_description(self):
        result = _get_interface_description("NIC.Slot.1-1")
        assert result == "NIC in Slot 1 Port 1"

    def test_idrac_description(self):
        result = _get_interface_description("iDRAC")
        assert result == "Dedicated iDRAC interface"

    def test_short_name_returns_empty(self):
        result = _get_interface_description("eth0")
        assert result == ""


class TestBuildInterfaceMapFromInventory:
    """Test cases for _build_interface_map_from_inventory function."""

    def test_build_map_with_interfaces(self):
        inventory = {
            "inventory": {
                "interfaces": [
                    {"mac_address": "AA:BB:CC:DD:EE:01", "name": "NIC.Slot.1-1"},
                    {"mac_address": "AA:BB:CC:DD:EE:02", "name": "NIC.Slot.1-2"},
                ]
            }
        }

        result = _build_interface_map_from_inventory(inventory)

        assert len(result) == 2
        assert result["aa:bb:cc:dd:ee:01"] == "NIC.Slot.1-1"
        assert result["aa:bb:cc:dd:ee:02"] == "NIC.Slot.1-2"

    def test_build_map_empty_inventory(self):
        result = _build_interface_map_from_inventory({})

        assert result == {}

    def test_build_map_skips_missing_mac(self):
        inventory = {
            "inventory": {
                "interfaces": [
                    {"name": "NIC.Slot.1-1"},  # Missing mac_address key
                    {"mac_address": "AA:BB:CC:DD:EE:02", "name": "NIC.Slot.1-2"},
                ]
            }
        }

        result = _build_interface_map_from_inventory(inventory)

        assert len(result) == 1


class TestBuildInterfacesFromPorts:
    """Test cases for _build_interfaces_from_ports function."""

    def test_build_interfaces_with_bios_name(self):
        node_uuid = str(uuid.uuid4())
        port_uuid = str(uuid.uuid4())

        port = MagicMock()
        port.uuid = port_uuid
        port.address = "aa:bb:cc:dd:ee:ff"
        port.extra = {"bios_name": "NIC.Slot.1-1"}
        port.local_link_connection = {
            "port_id": "Eth1/1",
            "switch_info": "switch1",
            "switch_id": "11:22:33:44:55:66",
        }
        port.pxe_enabled = True
        port.physical_network = "provisioning"
        port.name = None

        inventory_map = {}

        result = _build_interfaces_from_ports(node_uuid, [port], inventory_map)

        assert len(result) == 1
        iface = result[0]
        assert iface.uuid == port_uuid
        assert iface.name == "NIC.Slot.1-1"
        assert iface.mac_address == "AA:BB:CC:DD:EE:FF"
        assert iface.device_uuid == node_uuid
        assert iface.pxe_enabled is True
        assert iface.switch_port_id == "Eth1/1"
        assert iface.switch_info == "switch1"

    def test_build_interfaces_fallback_to_inventory_name(self):
        node_uuid = str(uuid.uuid4())
        port_uuid = str(uuid.uuid4())

        port = MagicMock()
        port.uuid = port_uuid
        port.address = "aa:bb:cc:dd:ee:ff"
        port.extra = {}
        port.local_link_connection = {}
        port.pxe_enabled = False
        port.physical_network = None
        port.name = None

        inventory_map = {"aa:bb:cc:dd:ee:ff": "NIC.Embedded.1-1-1"}

        result = _build_interfaces_from_ports(node_uuid, [port], inventory_map)

        assert result[0].name == "NIC.Embedded.1-1-1"

    def test_build_interfaces_fallback_to_port_uuid(self):
        node_uuid = str(uuid.uuid4())
        port_uuid = str(uuid.uuid4())

        port = MagicMock()
        port.uuid = port_uuid
        port.address = "aa:bb:cc:dd:ee:ff"
        port.extra = {}
        port.local_link_connection = {}
        port.pxe_enabled = False
        port.physical_network = None
        port.name = None

        result = _build_interfaces_from_ports(node_uuid, [port], {})

        assert result[0].name == port_uuid


class TestInterfaceInfo:
    """Test cases for InterfaceInfo dataclass."""

    def test_interface_info_defaults(self):
        iface = InterfaceInfo(
            uuid="test-uuid",
            name="NIC.Slot.1-1",
            mac_address="AA:BB:CC:DD:EE:FF",
            device_uuid="device-uuid",
        )

        assert iface.enabled is True
        assert iface.mgmt_only is False
        assert iface.pxe_enabled is False
        assert iface.interface_type == "unknown"


class TestCreateNautobotInterface:
    """Test cases for _create_nautobot_interface function."""

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    def test_create_interface_success(self, mock_nautobot):
        interface = InterfaceInfo(
            uuid="intf-uuid",
            name="NIC.Slot.1-1",
            mac_address="AA:BB:CC:DD:EE:FF",
            device_uuid="device-uuid",
            description="NIC in Slot 1 Port 1",
            interface_type="25gbase-x-sfp28",
        )

        mock_nautobot.dcim.interfaces.create.return_value = MagicMock(id="intf-uuid")

        _create_nautobot_interface(interface, mock_nautobot)

        mock_nautobot.dcim.interfaces.create.assert_called_once()
        call_kwargs = mock_nautobot.dcim.interfaces.create.call_args.kwargs
        assert call_kwargs["id"] == "intf-uuid"
        assert call_kwargs["name"] == "NIC.Slot.1-1"
        assert call_kwargs["mac_address"] == "AA:BB:CC:DD:EE:FF"
        assert call_kwargs["device"] == "device-uuid"

    def test_create_interface_handles_unique_constraint(self, mock_nautobot):
        interface = InterfaceInfo(
            uuid="intf-uuid",
            name="NIC.Slot.1-1",
            mac_address="AA:BB:CC:DD:EE:FF",
            device_uuid="device-uuid",
        )

        mock_nautobot.dcim.interfaces.create.side_effect = Exception(
            "unique constraint violation"
        )
        mock_nautobot.dcim.interfaces.get.return_value = MagicMock(id="intf-uuid")

        _create_nautobot_interface(interface, mock_nautobot)

        mock_nautobot.dcim.interfaces.get.assert_called_once_with(id="intf-uuid")


class TestUpdateNautobotInterface:
    """Test cases for _update_nautobot_interface function."""

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    @pytest.fixture
    def mock_nautobot_intf(self):
        intf = MagicMock()
        intf.name = "old-name"
        intf.mac_address = "00:00:00:00:00:00"
        intf.type = MagicMock(value="1000base-t")
        intf.description = ""
        intf.mgmt_only = False
        return intf

    def test_update_name(self, mock_nautobot, mock_nautobot_intf):
        interface = InterfaceInfo(
            uuid="intf-uuid",
            name="NIC.Slot.1-1",
            mac_address="AA:BB:CC:DD:EE:FF",
            device_uuid="device-uuid",
        )
        mock_nautobot.dcim.interfaces.get.return_value = None

        _update_nautobot_interface(interface, mock_nautobot_intf, mock_nautobot)

        assert mock_nautobot_intf.name == "NIC.Slot.1-1"
        mock_nautobot_intf.save.assert_called_once()

    def test_update_handles_name_conflict(self, mock_nautobot, mock_nautobot_intf):
        interface = InterfaceInfo(
            uuid="intf-uuid",
            name="NIC.Slot.1-1",
            mac_address="AA:BB:CC:DD:EE:FF",
            device_uuid="device-uuid",
        )

        conflicting_intf = MagicMock()
        conflicting_intf.id = "other-uuid"
        mock_nautobot.dcim.interfaces.get.return_value = conflicting_intf

        _update_nautobot_interface(interface, mock_nautobot_intf, mock_nautobot)

        conflicting_intf.delete.assert_called_once()

    def test_no_update_when_unchanged(self, mock_nautobot):
        interface = InterfaceInfo(
            uuid="intf-uuid",
            name="NIC.Slot.1-1",
            mac_address="AA:BB:CC:DD:EE:FF",
            device_uuid="device-uuid",
            interface_type="25gbase-x-sfp28",
        )

        nautobot_intf = MagicMock()
        nautobot_intf.name = "NIC.Slot.1-1"
        nautobot_intf.mac_address = "AA:BB:CC:DD:EE:FF"
        nautobot_intf.type = MagicMock(value="25gbase-x-sfp28")
        nautobot_intf.description = ""
        nautobot_intf.mgmt_only = False
        mock_nautobot.dcim.interfaces.get.return_value = None

        _update_nautobot_interface(interface, nautobot_intf, mock_nautobot)

        nautobot_intf.save.assert_not_called()


class TestSyncIdracInterface:
    """Test cases for sync_idrac_interface function."""

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    def test_create_idrac_interface(self, mock_nautobot):
        device_uuid = str(uuid.uuid4())
        bmc_mac = "aa:bb:cc:dd:ee:ff"

        mock_nautobot.dcim.interfaces.get.return_value = None
        mock_nautobot.dcim.interfaces.create.return_value = MagicMock(id="idrac-uuid")

        sync_idrac_interface(device_uuid, bmc_mac, mock_nautobot)

        mock_nautobot.dcim.interfaces.create.assert_called_once()
        call_kwargs = mock_nautobot.dcim.interfaces.create.call_args.kwargs
        assert call_kwargs["device"] == device_uuid
        assert call_kwargs["name"] == "iDRAC"
        assert call_kwargs["type"] == "1000base-t"
        assert call_kwargs["mac_address"] == "AA:BB:CC:DD:EE:FF"
        assert call_kwargs["mgmt_only"] is True

    def test_update_existing_idrac_interface(self, mock_nautobot):
        device_uuid = str(uuid.uuid4())
        bmc_mac = "aa:bb:cc:dd:ee:ff"

        existing_intf = MagicMock()
        existing_intf.mac_address = "00:00:00:00:00:00"
        mock_nautobot.dcim.interfaces.get.return_value = existing_intf

        sync_idrac_interface(device_uuid, bmc_mac, mock_nautobot)

        assert existing_intf.mac_address == "AA:BB:CC:DD:EE:FF"
        existing_intf.save.assert_called_once()

    def test_skip_when_no_bmc_mac(self, mock_nautobot):
        device_uuid = str(uuid.uuid4())

        sync_idrac_interface(device_uuid, "", mock_nautobot)

        mock_nautobot.dcim.interfaces.get.assert_not_called()

    def test_idrac_with_bmc_ip(self, mock_nautobot):
        device_uuid = str(uuid.uuid4())
        bmc_mac = "aa:bb:cc:dd:ee:ff"
        bmc_ip = "10.0.0.100"

        mock_nautobot.dcim.interfaces.get.return_value = None
        mock_intf = MagicMock()
        mock_intf.id = "idrac-uuid"
        mock_nautobot.dcim.interfaces.create.return_value = mock_intf
        mock_nautobot.ipam.ip_addresses.get.return_value = None
        mock_nautobot.ipam.ip_addresses.create.return_value = MagicMock(id="ip-uuid")
        mock_nautobot.ipam.ip_address_to_interface.get.return_value = None

        sync_idrac_interface(device_uuid, bmc_mac, mock_nautobot, bmc_ip)

        mock_nautobot.ipam.ip_addresses.create.assert_called_once()


class TestAssignIpToInterface:
    """Test cases for _assign_ip_to_interface function."""

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    def test_create_and_assign_ip(self, mock_nautobot):
        interface_id = "intf-uuid"
        ip_address = "10.0.0.100"

        mock_nautobot.ipam.ip_addresses.get.return_value = None
        mock_nautobot.ipam.ip_addresses.create.return_value = MagicMock(id="ip-uuid")
        mock_nautobot.ipam.ip_address_to_interface.get.return_value = None

        _assign_ip_to_interface(mock_nautobot, interface_id, ip_address)

        mock_nautobot.ipam.ip_addresses.create.assert_called_once_with(
            address=ip_address,
            status="Active",
        )
        mock_nautobot.ipam.ip_address_to_interface.create.assert_called_once()

    def test_use_existing_ip(self, mock_nautobot):
        interface_id = "intf-uuid"
        ip_address = "10.0.0.100"

        existing_ip = MagicMock()
        existing_ip.id = "existing-ip-uuid"
        mock_nautobot.ipam.ip_addresses.get.return_value = existing_ip
        mock_nautobot.ipam.ip_address_to_interface.get.return_value = None

        _assign_ip_to_interface(mock_nautobot, interface_id, ip_address)

        mock_nautobot.ipam.ip_addresses.create.assert_not_called()
        mock_nautobot.ipam.ip_address_to_interface.create.assert_called_once()

    def test_skip_if_already_associated(self, mock_nautobot):
        interface_id = "intf-uuid"
        ip_address = "10.0.0.100"

        existing_ip = MagicMock()
        existing_ip.id = "ip-uuid"
        mock_nautobot.ipam.ip_addresses.get.return_value = existing_ip

        existing_assoc = MagicMock()
        existing_assoc.interface.id = interface_id
        mock_nautobot.ipam.ip_address_to_interface.get.return_value = existing_assoc

        _assign_ip_to_interface(mock_nautobot, interface_id, ip_address)

        mock_nautobot.ipam.ip_address_to_interface.create.assert_not_called()

    def test_skip_empty_ip(self, mock_nautobot):
        _assign_ip_to_interface(mock_nautobot, "intf-uuid", "")

        mock_nautobot.ipam.ip_addresses.get.assert_not_called()


class TestHandleCableManagement:
    """Test cases for _handle_cable_management function."""

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    def test_create_cable(self, mock_nautobot):
        interface = InterfaceInfo(
            uuid="server-intf-uuid",
            name="NIC.Slot.1-1",
            mac_address="AA:BB:CC:DD:EE:FF",
            device_uuid="device-uuid",
            switch_info="switch1",
            switch_port_id="Eth1/1",
        )

        nautobot_intf = MagicMock()
        nautobot_intf.cable = None

        switch_intf = MagicMock()
        switch_intf.id = "switch-intf-uuid"
        mock_nautobot.dcim.interfaces.get.return_value = switch_intf

        _handle_cable_management(interface, nautobot_intf, mock_nautobot)

        mock_nautobot.dcim.cables.create.assert_called_once()
        call_kwargs = mock_nautobot.dcim.cables.create.call_args.kwargs
        assert call_kwargs["termination_a_id"] == "server-intf-uuid"
        assert call_kwargs["termination_b_id"] == "switch-intf-uuid"
        assert call_kwargs["status"] == "Connected"

    def test_skip_without_switch_info(self, mock_nautobot):
        interface = InterfaceInfo(
            uuid="server-intf-uuid",
            name="NIC.Slot.1-1",
            mac_address="AA:BB:CC:DD:EE:FF",
            device_uuid="device-uuid",
        )

        nautobot_intf = MagicMock()

        _handle_cable_management(interface, nautobot_intf, mock_nautobot)

        mock_nautobot.dcim.interfaces.get.assert_not_called()

    def test_skip_when_switch_interface_not_found(self, mock_nautobot):
        interface = InterfaceInfo(
            uuid="server-intf-uuid",
            name="NIC.Slot.1-1",
            mac_address="AA:BB:CC:DD:EE:FF",
            device_uuid="device-uuid",
            switch_info="switch1",
            switch_port_id="Eth1/1",
        )

        nautobot_intf = MagicMock()
        nautobot_intf.cable = None
        mock_nautobot.dcim.interfaces.get.return_value = None

        _handle_cable_management(interface, nautobot_intf, mock_nautobot)

        mock_nautobot.dcim.cables.create.assert_not_called()


class TestSyncInterfacesFromData:
    """Test cases for sync_interfaces_from_data function."""

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    def test_sync_interfaces_success(self, mock_nautobot):
        node_uuid = str(uuid.uuid4())
        port_uuid = str(uuid.uuid4())

        inventory = {
            "inventory": {
                "interfaces": [
                    {"mac_address": "aa:bb:cc:dd:ee:ff", "name": "NIC.Slot.1-1"}
                ],
                "bmc_mac": "11:22:33:44:55:66",
            }
        }

        port = MagicMock()
        port.uuid = port_uuid
        port.address = "aa:bb:cc:dd:ee:ff"
        port.extra = {}
        port.local_link_connection = {}
        port.pxe_enabled = False
        port.physical_network = None
        port.name = None

        mock_nautobot.dcim.interfaces.get.return_value = None
        mock_nautobot.dcim.interfaces.create.return_value = MagicMock()
        mock_nautobot.dcim.interfaces.filter.return_value = []

        result = sync_interfaces_from_data(node_uuid, inventory, [port], mock_nautobot)

        assert result == EXIT_STATUS_SUCCESS
        # Verify cleanup was called
        mock_nautobot.dcim.interfaces.filter.assert_called_with(device_id=node_uuid)

    def test_sync_interfaces_empty_uuid(self, mock_nautobot):
        result = sync_interfaces_from_data("", {}, [], mock_nautobot)

        assert result == EXIT_STATUS_FAILURE


class TestSyncInterfacesToNautobot:
    """Test cases for sync_interfaces_to_nautobot function."""

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    @patch(
        "understack_workflows.oslo_event.nautobot_device_interface_sync.IronicClient"
    )
    @patch(
        "understack_workflows.oslo_event.nautobot_device_interface_sync.sync_interfaces_from_data"
    )
    def test_sync_interfaces_success(
        self, mock_sync_from_data, mock_ironic_class, mock_nautobot
    ):
        node_uuid = str(uuid.uuid4())
        mock_ironic = MagicMock()
        mock_ironic_class.return_value = mock_ironic
        mock_ironic.get_node_inventory.return_value = {}
        mock_ironic.list_ports.return_value = []
        mock_sync_from_data.return_value = EXIT_STATUS_SUCCESS

        result = sync_interfaces_to_nautobot(node_uuid, mock_nautobot)

        assert result == EXIT_STATUS_SUCCESS
        mock_sync_from_data.assert_called_once()

    def test_sync_interfaces_empty_uuid(self, mock_nautobot):
        result = sync_interfaces_to_nautobot("", mock_nautobot)

        assert result == EXIT_STATUS_FAILURE


class TestExtractNodeUuidFromEvent:
    """Test cases for _extract_node_uuid_from_event function."""

    def test_extract_node_uuid_from_port_event(self):
        event_data = {
            "payload": {
                "ironic_object.data": {
                    "node_uuid": "12345678-1234-5678-9abc-123456789abc"
                }
            }
        }

        result = _extract_node_uuid_from_event(event_data)

        assert result == "12345678-1234-5678-9abc-123456789abc"

    def test_extract_uuid_from_node_event(self):
        event_data = {
            "payload": {
                "ironic_object.data": {"uuid": "12345678-1234-5678-9abc-123456789abc"}
            }
        }

        result = _extract_node_uuid_from_event(event_data)

        assert result == "12345678-1234-5678-9abc-123456789abc"

    def test_extract_returns_none_for_missing(self):
        event_data = {"payload": {"ironic_object.data": {}}}

        result = _extract_node_uuid_from_event(event_data)

        assert result is None


class TestHandleInterfaceSyncEvent:
    """Test cases for handle_interface_sync_event function."""

    @pytest.fixture
    def mock_conn(self):
        return MagicMock()

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    @patch(
        "understack_workflows.oslo_event.nautobot_device_interface_sync.sync_interfaces_to_nautobot"
    )
    def test_handle_event_success(self, mock_sync, mock_conn, mock_nautobot):
        node_uuid = str(uuid.uuid4())
        event_data = {
            "event_type": "baremetal.node.inspect.end",
            "payload": {
                "ironic_object.data": {
                    "uuid": node_uuid,
                }
            },
        }
        mock_sync.return_value = EXIT_STATUS_SUCCESS

        result = handle_interface_sync_event(mock_conn, mock_nautobot, event_data)

        assert result == EXIT_STATUS_SUCCESS
        mock_sync.assert_called_once_with(node_uuid, mock_nautobot)

    def test_handle_event_no_uuid(self, mock_conn, mock_nautobot):
        event_data = {"payload": {"ironic_object.data": {}}}

        result = handle_interface_sync_event(mock_conn, mock_nautobot, event_data)

        assert result == EXIT_STATUS_FAILURE


class TestDeleteNautobotInterface:
    """Test cases for _delete_nautobot_interface function."""

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    def test_delete_interface_with_cable(self, mock_nautobot):
        nautobot_intf = MagicMock()
        nautobot_intf.id = "intf-uuid"
        nautobot_intf.cable = MagicMock()

        _delete_nautobot_interface(nautobot_intf, mock_nautobot)

        nautobot_intf.cable.delete.assert_called_once()
        nautobot_intf.delete.assert_called_once()

    def test_delete_interface_without_cable(self, mock_nautobot):
        nautobot_intf = MagicMock()
        nautobot_intf.id = "intf-uuid"
        nautobot_intf.cable = None

        _delete_nautobot_interface(nautobot_intf, mock_nautobot)

        nautobot_intf.delete.assert_called_once()


class TestCleanupStaleInterfaces:
    """Test cases for _cleanup_stale_interfaces function."""

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    def test_delete_stale_interface(self, mock_nautobot):
        node_uuid = str(uuid.uuid4())
        valid_ids = {"valid-intf-1", "valid-intf-2"}

        stale_intf = MagicMock()
        stale_intf.id = "stale-intf"
        stale_intf.name = "NIC.Slot.1-1"
        stale_intf.cable = None

        valid_intf = MagicMock()
        valid_intf.id = "valid-intf-1"
        valid_intf.name = "NIC.Slot.1-2"

        mock_nautobot.dcim.interfaces.filter.return_value = [stale_intf, valid_intf]

        _cleanup_stale_interfaces(node_uuid, valid_ids, mock_nautobot)

        stale_intf.delete.assert_called_once()
        valid_intf.delete.assert_not_called()

    def test_skip_idrac_interface(self, mock_nautobot):
        node_uuid = str(uuid.uuid4())
        valid_ids = set()

        idrac_intf = MagicMock()
        idrac_intf.id = "idrac-intf"
        idrac_intf.name = "iDRAC"

        mock_nautobot.dcim.interfaces.filter.return_value = [idrac_intf]

        _cleanup_stale_interfaces(node_uuid, valid_ids, mock_nautobot)

        idrac_intf.delete.assert_not_called()

    def test_no_stale_interfaces(self, mock_nautobot):
        node_uuid = str(uuid.uuid4())
        valid_ids = {"intf-1", "intf-2"}

        intf1 = MagicMock()
        intf1.id = "intf-1"
        intf1.name = "NIC.Slot.1-1"

        intf2 = MagicMock()
        intf2.id = "intf-2"
        intf2.name = "NIC.Slot.1-2"

        mock_nautobot.dcim.interfaces.filter.return_value = [intf1, intf2]

        _cleanup_stale_interfaces(node_uuid, valid_ids, mock_nautobot)

        intf1.delete.assert_not_called()
        intf2.delete.assert_not_called()

    def test_handles_delete_failure(self, mock_nautobot):
        node_uuid = str(uuid.uuid4())
        valid_ids = set()

        stale_intf = MagicMock()
        stale_intf.id = "stale-intf"
        stale_intf.name = "NIC.Slot.1-1"
        stale_intf.cable = None
        stale_intf.delete.side_effect = Exception("Delete failed")

        mock_nautobot.dcim.interfaces.filter.return_value = [stale_intf]

        # Should not raise, just log warning
        _cleanup_stale_interfaces(node_uuid, valid_ids, mock_nautobot)
