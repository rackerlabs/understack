"""Tests for nautobot_device_sync module."""

import uuid
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from understack_workflows.oslo_event.nautobot_device_sync import EXIT_STATUS_FAILURE
from understack_workflows.oslo_event.nautobot_device_sync import EXIT_STATUS_SUCCESS
from understack_workflows.oslo_event.nautobot_device_sync import DeviceInfo
from understack_workflows.oslo_event.nautobot_device_sync import _create_nautobot_device
from understack_workflows.oslo_event.nautobot_device_sync import (
    _extract_node_uuid_from_event,
)
from understack_workflows.oslo_event.nautobot_device_sync import _generate_device_name
from understack_workflows.oslo_event.nautobot_device_sync import _get_record_value
from understack_workflows.oslo_event.nautobot_device_sync import _normalise_manufacturer
from understack_workflows.oslo_event.nautobot_device_sync import (
    _populate_from_inventory,
)
from understack_workflows.oslo_event.nautobot_device_sync import _populate_from_node
from understack_workflows.oslo_event.nautobot_device_sync import (
    _set_location_from_switches,
)
from understack_workflows.oslo_event.nautobot_device_sync import _update_nautobot_device
from understack_workflows.oslo_event.nautobot_device_sync import (
    delete_device_from_nautobot,
)
from understack_workflows.oslo_event.nautobot_device_sync import (
    handle_node_delete_event,
)
from understack_workflows.oslo_event.nautobot_device_sync import handle_node_event
from understack_workflows.oslo_event.nautobot_device_sync import sync_device_to_nautobot


class TestNormaliseManufacturer:
    """Test cases for _normalise_manufacturer function."""

    def test_normalise_dell_uppercase(self):
        assert _normalise_manufacturer("DELL INC.") == "Dell"

    def test_normalise_dell_lowercase(self):
        assert _normalise_manufacturer("dell") == "Dell"

    def test_normalise_dell_mixed_case(self):
        assert _normalise_manufacturer("Dell Inc.") == "Dell"

    def test_normalise_hp(self):
        assert _normalise_manufacturer("HP") == "HP"

    def test_unsupported_manufacturer_raises(self):
        with pytest.raises(ValueError, match="not supported"):
            _normalise_manufacturer("Lenovo")


class TestPopulateFromNode:
    """Test cases for _populate_from_node function."""

    @pytest.fixture
    def device_info(self):
        return DeviceInfo(uuid="test-uuid")

    @pytest.fixture
    def mock_node(self):
        node = MagicMock()
        node.properties = {
            "memory_mb": 65536,
            "cpus": 32,
            "cpu_arch": "x86_64",
            "local_gb": 500,
        }
        node.traits = ["CUSTOM_TRAIT1", "CUSTOM_TRAIT2"]
        node.provision_state = "active"
        node.lessee = "12345678-1234-5678-9abc-123456789abc"
        return node

    def test_populate_all_fields(self, device_info, mock_node):
        _populate_from_node(device_info, mock_node)

        assert device_info.memory_mb == 65536
        assert device_info.cpus == 32
        assert device_info.cpu_arch == "x86_64"
        assert device_info.local_gb == 500
        assert device_info.traits == ["CUSTOM_TRAIT1", "CUSTOM_TRAIT2"]
        assert device_info.status == "Active"
        assert device_info.tenant_id == "12345678-1234-5678-9abc-123456789abc"

    def test_populate_with_empty_properties(self, device_info):
        node = MagicMock()
        node.properties = {}
        node.traits = None
        node.provision_state = "enroll"
        node.lessee = None

        _populate_from_node(device_info, node)

        assert device_info.manufacturer is None
        assert device_info.memory_mb is None
        assert device_info.cpus is None
        assert device_info.traits == []
        assert device_info.tenant_id is None

    def test_populate_with_invalid_lessee(self, device_info):
        node = MagicMock()
        node.properties = {}
        node.traits = None
        node.provision_state = "active"
        node.lessee = "invalid-uuid"

        _populate_from_node(device_info, node)

        assert device_info.tenant_id is None


class TestPopulateFromInventory:
    """Test cases for _populate_from_inventory function."""

    @pytest.fixture
    def device_info(self):
        return DeviceInfo(uuid="test-uuid")

    def test_populate_from_inventory_full(self, device_info):
        inventory = {
            "inventory": {
                "system_vendor": {
                    "manufacturer": "Dell Inc.",
                    "product_name": "PowerEdge R7615 (SKU=0AF7)",
                    "sku": "ABC1234",
                    "serial_number": "SN123456",
                }
            }
        }

        _populate_from_inventory(device_info, inventory)

        assert device_info.manufacturer == "Dell"
        assert device_info.model == "PowerEdge R7615"
        assert device_info.service_tag == "ABC1234"
        assert device_info.serial_number == "SN123456"

    def test_populate_from_inventory_agent_format(self, device_info):
        """Test AGENT inspection format (no sku, serial_number as service tag)."""
        inventory = {
            "inventory": {
                "system_vendor": {
                    "manufacturer": "Dell Inc.",
                    "product_name": "PowerEdge R640",
                    "serial_number": "SERVICETAG123",
                }
            }
        }

        _populate_from_inventory(device_info, inventory)

        assert device_info.service_tag == "SERVICETAG123"
        assert device_info.serial_number is None  # Only set when sku exists

    def test_populate_from_inventory_empty(self, device_info):
        _populate_from_inventory(device_info, None)

        assert device_info.model is None
        assert device_info.service_tag is None

    def test_populate_from_inventory_system_product_name(self, device_info):
        """Test that 'System' product name is ignored."""
        inventory = {
            "inventory": {
                "system_vendor": {
                    "product_name": "System",
                }
            }
        }

        _populate_from_inventory(device_info, inventory)

        assert device_info.model is None

    def test_manufacturer_fallback(self, device_info):
        """Test manufacturer is set from inventory."""
        device_info.manufacturer = "Dell"  # Already set
        inventory = {
            "inventory": {
                "system_vendor": {
                    "manufacturer": "HP",  # Different
                }
            }
        }

        _populate_from_inventory(device_info, inventory)

        # Inventory always sets manufacturer
        assert device_info.manufacturer == "HP"


class TestGenerateDeviceName:
    """Test cases for _generate_device_name function."""

    def test_generate_name_with_both_fields(self):
        device_info = DeviceInfo(
            uuid="test-uuid",
            manufacturer="Dell",
            service_tag="ABC1234",
        )

        _generate_device_name(device_info)

        assert device_info.name == "Dell-ABC1234"

    def test_generate_name_missing_manufacturer(self):
        device_info = DeviceInfo(
            uuid="test-uuid",
            service_tag="ABC1234",
        )

        _generate_device_name(device_info)

        assert device_info.name is None

    def test_generate_name_missing_service_tag(self):
        device_info = DeviceInfo(
            uuid="test-uuid",
            manufacturer="Dell",
        )

        _generate_device_name(device_info)

        assert device_info.name is None


class TestSetLocationFromSwitches:
    """Test cases for _set_location_from_switches function."""

    @pytest.fixture
    def device_info(self):
        return DeviceInfo(uuid="test-uuid")

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    def test_set_location_from_switch_info(self, device_info, mock_nautobot):
        ports = [
            MagicMock(
                local_link_connection={
                    "switch_info": "switch1.example.com",
                    "switch_id": "aa:bb:cc:dd:ee:ff",
                }
            )
        ]

        mock_device = MagicMock()
        mock_device.location.id = "location-uuid"
        mock_device.rack.id = "rack-uuid"
        mock_nautobot.dcim.devices.get.return_value = mock_device

        _set_location_from_switches(device_info, ports, mock_nautobot)

        assert device_info.location_id == "location-uuid"
        assert device_info.rack_id == "rack-uuid"

    def test_set_location_no_switch_info(self, device_info, mock_nautobot):
        ports = [MagicMock(local_link_connection={})]

        _set_location_from_switches(device_info, ports, mock_nautobot)

        assert device_info.location_id is None
        assert device_info.rack_id is None

    def test_set_location_switch_info_is_string_none(self, device_info, mock_nautobot):
        """Test that literal string 'None' in switch_info is skipped."""
        ports = [
            MagicMock(
                local_link_connection={
                    "switch_info": "None",
                    "switch_id": "00:00:00:00:00:00",
                    "port_id": "None",
                }
            )
        ]

        _set_location_from_switches(device_info, ports, mock_nautobot)

        # Should not make any API calls
        mock_nautobot.dcim.devices.get.assert_not_called()
        assert device_info.location_id is None
        assert device_info.rack_id is None

    def test_set_location_switch_not_found(self, device_info, mock_nautobot):
        ports = [
            MagicMock(
                local_link_connection={
                    "switch_info": "unknown-switch",
                }
            )
        ]
        mock_nautobot.dcim.devices.get.return_value = None
        mock_nautobot.dcim.interfaces.filter.return_value = []

        _set_location_from_switches(device_info, ports, mock_nautobot)

        assert device_info.location_id is None


class TestGetRecordValue:
    """Test cases for _get_record_value function."""

    def test_get_value_from_record(self):
        record = MagicMock()
        record.value = "test-value"

        assert _get_record_value(record) == "test-value"

    def test_get_id_from_record(self):
        record = MagicMock()
        record.id = "test-id"

        assert _get_record_value(record, "id") == "test-id"

    def test_get_value_from_none(self):
        assert _get_record_value(None) is None

    def test_get_value_from_primitive(self):
        assert _get_record_value("simple-string") == "simple-string"


class TestCreateNautobotDevice:
    """Test cases for _create_nautobot_device function."""

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    def test_create_device_success(self, mock_nautobot):
        device_info = DeviceInfo(
            uuid="test-uuid",
            name="Dell-ABC123",
            manufacturer="Dell",
            model="PowerEdge R640",
            location_id="location-uuid",
            role="server",
        )

        mock_nautobot.dcim.devices.create.return_value = MagicMock(id="test-uuid")

        _create_nautobot_device(device_info, mock_nautobot)

        mock_nautobot.dcim.devices.create.assert_called_once()
        call_kwargs = mock_nautobot.dcim.devices.create.call_args.kwargs
        assert call_kwargs["id"] == "test-uuid"
        assert call_kwargs["name"] == "Dell-ABC123"
        assert call_kwargs["location"] == "location-uuid"

    def test_create_device_without_location_raises(self, mock_nautobot):
        device_info = DeviceInfo(
            uuid="test-uuid",
            name="Dell-ABC123",
        )

        with pytest.raises(ValueError, match="without location"):
            _create_nautobot_device(device_info, mock_nautobot)

    def test_create_device_fallback_name_to_uuid(self, mock_nautobot):
        device_info = DeviceInfo(
            uuid="test-uuid",
            manufacturer="Dell",
            model="PowerEdge R640",
            location_id="location-uuid",
        )

        _create_nautobot_device(device_info, mock_nautobot)

        call_kwargs = mock_nautobot.dcim.devices.create.call_args.kwargs
        assert call_kwargs["name"] == "test-uuid"


class TestUpdateNautobotDevice:
    """Test cases for _update_nautobot_device function."""

    @pytest.fixture
    def mock_nautobot_device(self):
        device = MagicMock()
        device.status = MagicMock(name="Planned")
        device.name = "Old-Name"
        device.serial = None
        device.location = MagicMock(id="old-location")
        device.rack = MagicMock(id="old-rack")
        device.tenant = None
        device.custom_fields = {}
        return device

    def test_update_status(self, mock_nautobot_device):
        device_info = DeviceInfo(uuid="test-uuid", status="Active")

        result = _update_nautobot_device(device_info, mock_nautobot_device)

        assert result is True
        mock_nautobot_device.save.assert_called_once()

    def test_update_name(self, mock_nautobot_device):
        device_info = DeviceInfo(uuid="test-uuid", name="New-Name")

        result = _update_nautobot_device(device_info, mock_nautobot_device)

        assert result is True
        assert mock_nautobot_device.name == "New-Name"

    def test_update_tenant(self, mock_nautobot_device):
        device_info = DeviceInfo(
            uuid="test-uuid",
            tenant_id="12345678-1234-5678-9abc-123456789abc",
        )

        result = _update_nautobot_device(device_info, mock_nautobot_device)

        assert result is True
        assert mock_nautobot_device.tenant == "12345678-1234-5678-9abc-123456789abc"

    def test_no_changes(self, mock_nautobot_device):
        device_info = DeviceInfo(uuid="test-uuid")

        result = _update_nautobot_device(device_info, mock_nautobot_device)

        assert result is False
        mock_nautobot_device.save.assert_not_called()


class TestExtractNodeUuidFromEvent:
    """Test cases for _extract_node_uuid_from_event function."""

    def test_extract_from_payload(self):
        event_data = {
            "payload": {
                "ironic_object.data": {"uuid": "12345678-1234-5678-9abc-123456789abc"}
            }
        }

        result = _extract_node_uuid_from_event(event_data)

        assert result == "12345678-1234-5678-9abc-123456789abc"

    def test_extract_from_ironic_object(self):
        event_data = {"ironic_object": {"uuid": "12345678-1234-5678-9abc-123456789abc"}}

        result = _extract_node_uuid_from_event(event_data)

        assert result == "12345678-1234-5678-9abc-123456789abc"

    def test_extract_returns_none_for_missing_uuid(self):
        event_data = {"payload": {"ironic_object.data": {}}}

        result = _extract_node_uuid_from_event(event_data)

        assert result is None


class TestSyncDeviceToNautobot:
    """Test cases for sync_device_to_nautobot function."""

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    @patch("understack_workflows.oslo_event.nautobot_device_sync.IronicClient")
    @patch("understack_workflows.oslo_event.nautobot_device_sync.fetch_device_info")
    @patch(
        "understack_workflows.oslo_event.nautobot_device_sync.sync_interfaces_from_data"
    )
    def test_sync_creates_new_device(
        self, mock_sync_interfaces, mock_fetch, mock_ironic_class, mock_nautobot
    ):
        node_uuid = str(uuid.uuid4())
        device_info = DeviceInfo(
            uuid=node_uuid,
            name="Dell-ABC123",
            manufacturer="Dell",
            model="PowerEdge R640",
            location_id="location-uuid",
            status="Active",
        )
        mock_fetch.return_value = (device_info, {}, [])
        mock_nautobot.dcim.devices.get.return_value = None
        mock_nautobot.dcim.devices.create.return_value = MagicMock()
        mock_sync_interfaces.return_value = EXIT_STATUS_SUCCESS

        result = sync_device_to_nautobot(node_uuid, mock_nautobot)

        assert result == EXIT_STATUS_SUCCESS
        mock_nautobot.dcim.devices.create.assert_called_once()

    @patch("understack_workflows.oslo_event.nautobot_device_sync.IronicClient")
    @patch("understack_workflows.oslo_event.nautobot_device_sync.fetch_device_info")
    @patch(
        "understack_workflows.oslo_event.nautobot_device_sync.sync_interfaces_from_data"
    )
    def test_sync_updates_existing_device(
        self, mock_sync_interfaces, mock_fetch, mock_ironic_class, mock_nautobot
    ):
        node_uuid = str(uuid.uuid4())
        device_info = DeviceInfo(
            uuid=node_uuid,
            name="Dell-ABC123",
            status="Active",
        )
        mock_fetch.return_value = (device_info, {}, [])

        existing_device = MagicMock()
        existing_device.status = MagicMock(name="Planned")
        existing_device.name = "Dell-ABC123"
        existing_device.serial = None
        existing_device.location = None
        existing_device.rack = None
        existing_device.tenant = None
        existing_device.custom_fields = {}
        mock_nautobot.dcim.devices.get.return_value = existing_device
        mock_sync_interfaces.return_value = EXIT_STATUS_SUCCESS

        result = sync_device_to_nautobot(node_uuid, mock_nautobot)

        assert result == EXIT_STATUS_SUCCESS
        mock_nautobot.dcim.devices.create.assert_not_called()

    def test_sync_with_empty_uuid_returns_error(self, mock_nautobot):
        result = sync_device_to_nautobot("", mock_nautobot)

        assert result == EXIT_STATUS_FAILURE

    @patch("understack_workflows.oslo_event.nautobot_device_sync.IronicClient")
    @patch("understack_workflows.oslo_event.nautobot_device_sync.fetch_device_info")
    def test_sync_without_location_returns_error(
        self, mock_fetch, mock_ironic_class, mock_nautobot
    ):
        node_uuid = str(uuid.uuid4())
        device_info = DeviceInfo(uuid=node_uuid)  # No location
        mock_fetch.return_value = (device_info, {}, [])
        mock_nautobot.dcim.devices.get.return_value = None

        result = sync_device_to_nautobot(node_uuid, mock_nautobot)

        assert result == EXIT_STATUS_FAILURE

    @patch("understack_workflows.oslo_event.nautobot_device_sync.IronicClient")
    @patch("understack_workflows.oslo_event.nautobot_device_sync.fetch_device_info")
    @patch(
        "understack_workflows.oslo_event.nautobot_device_sync.sync_interfaces_from_data"
    )
    def test_sync_finds_device_by_name_with_matching_uuid(
        self, mock_sync_interfaces, mock_fetch, mock_ironic_class, mock_nautobot
    ):
        """Test that device found by name with matching UUID is updated."""
        node_uuid = str(uuid.uuid4())
        device_info = DeviceInfo(
            uuid=node_uuid,
            name="Dell-ABC123",
            manufacturer="Dell",
            model="PowerEdge R640",
            location_id="location-uuid",
            status="Active",
        )
        mock_fetch.return_value = (device_info, {}, [])

        # First get by ID returns None
        # Second get by name returns device with same UUID
        existing_device = MagicMock()
        existing_device.id = node_uuid  # Same UUID
        existing_device.status = MagicMock(name="Planned")
        existing_device.name = "Dell-ABC123"
        existing_device.serial = None
        existing_device.location = None
        existing_device.rack = None
        existing_device.tenant = None
        existing_device.custom_fields = {}

        mock_nautobot.dcim.devices.get.side_effect = [None, existing_device]
        mock_sync_interfaces.return_value = EXIT_STATUS_SUCCESS

        result = sync_device_to_nautobot(node_uuid, mock_nautobot)

        assert result == EXIT_STATUS_SUCCESS
        # Should NOT delete since UUIDs match
        existing_device.delete.assert_not_called()
        # Should NOT create new device
        mock_nautobot.dcim.devices.create.assert_not_called()

    @patch("understack_workflows.oslo_event.nautobot_device_sync.IronicClient")
    @patch("understack_workflows.oslo_event.nautobot_device_sync.fetch_device_info")
    @patch(
        "understack_workflows.oslo_event.nautobot_device_sync.sync_interfaces_from_data"
    )
    def test_sync_recreates_device_with_mismatched_uuid(
        self, mock_sync_interfaces, mock_fetch, mock_ironic_class, mock_nautobot
    ):
        """Test device with mismatched UUID is deleted and recreated."""
        node_uuid = str(uuid.uuid4())
        old_uuid = str(uuid.uuid4())  # Different UUID
        device_info = DeviceInfo(
            uuid=node_uuid,
            name="Dell-ABC123",
            manufacturer="Dell",
            model="PowerEdge R640",
            location_id="location-uuid",
            status="Active",
        )
        mock_fetch.return_value = (device_info, {}, [])

        # First get by ID returns None
        # Second get by name returns device with different UUID
        existing_device = MagicMock()
        existing_device.id = old_uuid  # Different UUID
        existing_device.status = MagicMock(name="Planned")
        existing_device.name = "Dell-ABC123"

        mock_nautobot.dcim.devices.get.side_effect = [None, existing_device]
        mock_nautobot.dcim.devices.create.return_value = MagicMock()
        mock_sync_interfaces.return_value = EXIT_STATUS_SUCCESS

        result = sync_device_to_nautobot(node_uuid, mock_nautobot)

        assert result == EXIT_STATUS_SUCCESS
        # Should delete old device
        existing_device.delete.assert_called_once()
        # Should create new device with correct UUID
        mock_nautobot.dcim.devices.create.assert_called_once()

    @patch("understack_workflows.oslo_event.nautobot_device_sync.IronicClient")
    @patch("understack_workflows.oslo_event.nautobot_device_sync.fetch_device_info")
    @patch(
        "understack_workflows.oslo_event.nautobot_device_sync.sync_interfaces_from_data"
    )
    def test_sync_device_not_found_by_name_creates_new(
        self, mock_sync_interfaces, mock_fetch, mock_ironic_class, mock_nautobot
    ):
        """Test that device not found by UUID or name is created."""
        node_uuid = str(uuid.uuid4())
        device_info = DeviceInfo(
            uuid=node_uuid,
            name="Dell-ABC123",
            manufacturer="Dell",
            model="PowerEdge R640",
            location_id="location-uuid",
            status="Active",
        )
        mock_fetch.return_value = (device_info, {}, [])

        # Both lookups return None
        mock_nautobot.dcim.devices.get.side_effect = [None, None]
        mock_nautobot.dcim.devices.create.return_value = MagicMock()
        mock_sync_interfaces.return_value = EXIT_STATUS_SUCCESS

        result = sync_device_to_nautobot(node_uuid, mock_nautobot)

        assert result == EXIT_STATUS_SUCCESS
        mock_nautobot.dcim.devices.create.assert_called_once()


class TestDeleteDeviceFromNautobot:
    """Test cases for delete_device_from_nautobot function."""

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    def test_delete_existing_device(self, mock_nautobot):
        node_uuid = str(uuid.uuid4())
        mock_device = MagicMock()
        mock_nautobot.dcim.devices.get.return_value = mock_device

        result = delete_device_from_nautobot(node_uuid, mock_nautobot)

        assert result == EXIT_STATUS_SUCCESS
        mock_device.delete.assert_called_once()

    def test_delete_nonexistent_device(self, mock_nautobot):
        node_uuid = str(uuid.uuid4())
        mock_nautobot.dcim.devices.get.return_value = None

        result = delete_device_from_nautobot(node_uuid, mock_nautobot)

        assert result == EXIT_STATUS_SUCCESS

    def test_delete_with_empty_uuid(self, mock_nautobot):
        result = delete_device_from_nautobot("", mock_nautobot)

        assert result == EXIT_STATUS_FAILURE


class TestHandleNodeEvent:
    """Test cases for handle_node_event function."""

    @pytest.fixture
    def mock_conn(self):
        return MagicMock()

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    @patch(
        "understack_workflows.oslo_event.nautobot_device_sync.sync_device_to_nautobot"
    )
    def test_handle_node_event_success(self, mock_sync, mock_conn, mock_nautobot):
        node_uuid = str(uuid.uuid4())
        event_data = {
            "event_type": "baremetal.node.provision_set.end",
            "payload": {
                "ironic_object.data": {
                    "uuid": node_uuid,
                }
            },
        }
        mock_sync.return_value = EXIT_STATUS_SUCCESS

        result = handle_node_event(mock_conn, mock_nautobot, event_data)

        assert result == EXIT_STATUS_SUCCESS
        mock_sync.assert_called_once_with(node_uuid, mock_nautobot)

    def test_handle_node_event_no_uuid(self, mock_conn, mock_nautobot):
        event_data = {"payload": {"ironic_object.data": {}}}

        result = handle_node_event(mock_conn, mock_nautobot, event_data)

        assert result == EXIT_STATUS_FAILURE


class TestHandleNodeDeleteEvent:
    """Test cases for handle_node_delete_event function."""

    @pytest.fixture
    def mock_conn(self):
        return MagicMock()

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    @patch(
        "understack_workflows.oslo_event.nautobot_device_sync.delete_device_from_nautobot"
    )
    def test_handle_delete_event_success(self, mock_delete, mock_conn, mock_nautobot):
        node_uuid = str(uuid.uuid4())
        event_data = {
            "payload": {
                "ironic_object.data": {
                    "uuid": node_uuid,
                }
            },
        }
        mock_delete.return_value = EXIT_STATUS_SUCCESS

        result = handle_node_delete_event(mock_conn, mock_nautobot, event_data)

        assert result == EXIT_STATUS_SUCCESS
        mock_delete.assert_called_once_with(node_uuid, mock_nautobot)
