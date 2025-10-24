import json
import uuid
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from understack_workflows.oslo_event.ironic_node import IronicProvisionSetEvent
from understack_workflows.oslo_event.ironic_node import create_volume_connector
from understack_workflows.oslo_event.ironic_node import handle_provision_end
from understack_workflows.oslo_event.ironic_node import instance_nqn


def _sample_fixture_data(name: str) -> dict:
    """Load example data from JSON fixture file."""
    with open(f"tests/json_samples/{name}.json") as f:
        return json.load(f)


class TestIronicProvisionSetEvent:
    """Test cases for IronicProvisionSetEvent class."""

    def test_from_event_dict_success(self):
        """Test successful event parsing with real JSON data."""
        # Load real event data from JSON sample
        json_file = (
            "tests/json_samples/ironic_versioned_notifications_server_provisioned.json"
        )
        with open(json_file) as f:
            sample_data = json.load(f)

        # Parse the oslo message to get the actual event data
        oslo_message = json.loads(sample_data["oslomessage"])

        # Create event data in the format expected by from_event_dict
        ironic_data = oslo_message["payload"]["ironic_object.data"]
        event_data = {
            "instance_uuid": ironic_data["instance_uuid"],
            "payload": oslo_message["payload"],
        }

        event = IronicProvisionSetEvent.from_event_dict(event_data)

        # Verify the parsed values match the real data
        # UUIDs are formatted with hyphens when converted to UUID objects
        assert str(event.owner) == "32e02632-f4f0-4415-bab5-895d1e7247b7"
        assert str(event.lessee) == "5f5955bc-89e1-48e5-9a12-110a3945e4d7"
        assert str(event.instance_uuid) == "5027885e-52a8-48f9-adf4-14d8f5f4ccb8"
        assert str(event.node_uuid) == "461737c4-037c-41bf-9c17-f4f33ff20dd7"
        assert event.event == "done"

    def test_from_event_dict_no_payload(self):
        """Test event parsing with missing payload."""
        event_data = {"instance_uuid": uuid.uuid4()}

        with pytest.raises(ValueError, match="invalid event"):
            IronicProvisionSetEvent.from_event_dict(event_data)

    def test_from_event_dict_no_ironic_object_data(self):
        """Test event parsing with missing ironic_object.data."""
        event_data = {
            "instance_uuid": uuid.uuid4(),
            "payload": {"other_field": "value"},
        }

        with pytest.raises(
            ValueError, match="Invalid event. No 'ironic_object.data' in payload"
        ):
            IronicProvisionSetEvent.from_event_dict(event_data)

    def test_from_event_dict_missing_required_fields(self):
        """Test event parsing with missing required fields in ironic_object.data."""
        event_data = {
            "instance_uuid": uuid.uuid4(),
            "payload": {
                "ironic_object.data": {
                    "owner": uuid.uuid4(),
                    # Missing lessee, event, uuid
                }
            },
        }

        with pytest.raises(KeyError):
            IronicProvisionSetEvent.from_event_dict(event_data)

    def test_direct_initialization(self):
        """Test direct initialization of IronicProvisionSetEvent."""
        owner_uuid = uuid.uuid4()
        lessee_uuid = uuid.uuid4()
        instance_uuid = uuid.uuid4()
        node_uuid = uuid.uuid4()
        event_type = "provision_end"

        event = IronicProvisionSetEvent(
            owner=owner_uuid,
            lessee=lessee_uuid,
            instance_uuid=instance_uuid,
            node_uuid=node_uuid,
            event=event_type,
        )

        assert event.owner == owner_uuid
        assert event.lessee == lessee_uuid
        assert event.instance_uuid == instance_uuid
        assert event.node_uuid == node_uuid
        assert event.event == event_type


class TestHandleProvisionEnd:
    """Test cases for handle_provision_end function."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock OpenStack connection."""
        return MagicMock()

    @pytest.fixture
    def mock_nautobot(self):
        """Create a mock Nautobot instance."""
        return MagicMock()

    @pytest.fixture
    def valid_event_data(self):
        """Create valid event data for testing."""
        return {
            "payload": {
                "ironic_object.data": {
                    "instance_uuid": uuid.uuid4(),
                    "owner": uuid.uuid4(),
                    "lessee": uuid.uuid4(),
                    "event": "provision_end",
                    "uuid": uuid.uuid4(),
                    "previous_provision_state": "deploying",
                }
            },
        }

    @patch("understack_workflows.oslo_event.update_nautobot.handle_provision_end")
    def test_handle_provision_end_previous_state_inspecting(
        self, mock_update_nautobot_handler, mock_conn, mock_nautobot, valid_event_data
    ):
        """Returns early when previous_provision_state is 'inspecting'.

        Note: When state is 'inspecting', the update_nautobot handler is responsible
        for processing the event (both handlers are registered for provision_set.end).
        """
        valid_event_data["payload"]["ironic_object.data"][
            "previous_provision_state"
        ] = "inspecting"

        # Test ironic_node handler returns early
        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        assert result == 0
        # should return early without calling storage-related methods
        mock_conn.get_server_by_id.assert_not_called()

        # Demonstrate that update_nautobot handler would process this event
        from understack_workflows.oslo_event import update_nautobot

        mock_update_nautobot_handler.return_value = 0
        result = update_nautobot.handle_provision_end(
            mock_conn, mock_nautobot, valid_event_data
        )
        mock_update_nautobot_handler.assert_called_once_with(
            mock_conn, mock_nautobot, valid_event_data
        )

    @patch("understack_workflows.oslo_event.ironic_node.is_project_svm_enabled")
    def test_handle_provision_end_project_not_svm_enabled(
        self, mock_is_svm_enabled, mock_conn, mock_nautobot, valid_event_data
    ):
        """Test handling when project is not SVM enabled."""
        mock_is_svm_enabled.return_value = False

        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        assert result == 0
        lessee_uuid = valid_event_data["payload"]["ironic_object.data"]["lessee"]
        mock_is_svm_enabled.assert_called_once_with(mock_conn, str(lessee_uuid.hex))

    @patch("understack_workflows.oslo_event.ironic_node.create_volume_connector")
    @patch("understack_workflows.oslo_event.ironic_node.save_output")
    @patch("understack_workflows.oslo_event.ironic_node.is_project_svm_enabled")
    def test_handle_provision_end_server_not_found(
        self,
        mock_is_svm_enabled,
        mock_save_output,
        mock_create_connector,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when server is not found."""
        mock_is_svm_enabled.return_value = True
        mock_conn.get_server_by_id.return_value = None

        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        assert result == 1
        instance_uuid = valid_event_data["payload"]["ironic_object.data"][
            "instance_uuid"
        ]
        mock_conn.get_server_by_id.assert_called_once_with(instance_uuid)
        mock_save_output.assert_called_once_with("storage", "not-found")
        mock_create_connector.assert_not_called()

    @patch("understack_workflows.oslo_event.ironic_node.create_volume_connector")
    @patch("understack_workflows.oslo_event.ironic_node.save_output")
    @patch("understack_workflows.oslo_event.ironic_node.is_project_svm_enabled")
    def test_handle_provision_end_storage_wanted(
        self,
        mock_is_svm_enabled,
        mock_save_output,
        mock_create_connector,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when server wants storage."""
        mock_is_svm_enabled.return_value = True
        mock_server = MagicMock()
        mock_server.id = "server-123"
        mock_server.metadata = {"storage": "wanted"}
        mock_conn.get_server_by_id.return_value = mock_server

        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        assert result == 0
        ironic_data = valid_event_data["payload"]["ironic_object.data"]
        instance_uuid = ironic_data["instance_uuid"]
        node_uuid = ironic_data["uuid"]

        mock_conn.get_server_by_id.assert_called_once_with(instance_uuid)

        # Check save_output calls
        expected_calls = [
            ("storage", "wanted"),
            ("node_uuid", str(node_uuid)),
            ("instance_uuid", str(instance_uuid)),
        ]
        actual_calls = [call.args for call in mock_save_output.call_args_list]
        assert actual_calls == expected_calls

        mock_create_connector.assert_called_once()

    @patch("understack_workflows.oslo_event.ironic_node.create_volume_connector")
    @patch("understack_workflows.oslo_event.ironic_node.save_output")
    @patch("understack_workflows.oslo_event.ironic_node.is_project_svm_enabled")
    def test_handle_provision_end_storage_not_wanted(
        self,
        mock_is_svm_enabled,
        mock_save_output,
        mock_create_connector,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when server does not want storage."""
        mock_is_svm_enabled.return_value = True
        mock_server = MagicMock()
        mock_server.id = "server-123"
        mock_server.metadata = {"storage": "not-wanted"}
        mock_conn.get_server_by_id.return_value = mock_server

        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        assert result == 0
        ironic_data = valid_event_data["payload"]["ironic_object.data"]
        instance_uuid = ironic_data["instance_uuid"]
        node_uuid = ironic_data["uuid"]

        mock_conn.get_server_by_id.assert_called_once_with(instance_uuid)

        # Check save_output calls
        expected_calls = [
            ("storage", "not-set"),
            ("node_uuid", str(node_uuid)),
            ("instance_uuid", str(instance_uuid)),
        ]
        actual_calls = [call.args for call in mock_save_output.call_args_list]
        assert actual_calls == expected_calls

        mock_create_connector.assert_called_once()

    @patch("understack_workflows.oslo_event.ironic_node.create_volume_connector")
    @patch("understack_workflows.oslo_event.ironic_node.save_output")
    @patch("understack_workflows.oslo_event.ironic_node.is_project_svm_enabled")
    def test_handle_provision_end_storage_metadata_missing(
        self,
        mock_is_svm_enabled,
        mock_save_output,
        mock_create_connector,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when server metadata doesn't have storage key."""
        mock_is_svm_enabled.return_value = True
        mock_server = MagicMock()
        mock_server.id = "server-123"
        mock_server.metadata = {"other_key": "value"}
        mock_conn.get_server_by_id.return_value = mock_server

        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        assert result == 0
        ironic_data = valid_event_data["payload"]["ironic_object.data"]
        instance_uuid = ironic_data["instance_uuid"]
        node_uuid = ironic_data["uuid"]

        mock_conn.get_server_by_id.assert_called_once_with(instance_uuid)

        # When storage key is missing, it should be treated as "not-set"
        expected_calls = [
            ("storage", "not-set"),
            ("node_uuid", str(node_uuid)),
            ("instance_uuid", str(instance_uuid)),
        ]
        actual_calls = [call.args for call in mock_save_output.call_args_list]
        assert actual_calls == expected_calls

        mock_create_connector.assert_called_once()

    @patch("understack_workflows.oslo_event.ironic_node.is_project_svm_enabled")
    def test_handle_provision_end_invalid_event_data(
        self, mock_is_svm_enabled, mock_conn, mock_nautobot
    ):
        """Test handling with invalid event data."""
        invalid_event_data = {"instance_uuid": uuid.uuid4(), "payload": {}}

        with pytest.raises(
            ValueError, match="Invalid event. No 'ironic_object.data' in payload"
        ):
            handle_provision_end(mock_conn, mock_nautobot, invalid_event_data)

        mock_is_svm_enabled.assert_not_called()


class TestCreateVolumeConnector:
    """Test cases for create_volume_connector function."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock OpenStack connection."""
        return MagicMock()

    @pytest.fixture
    def sample_event(self):
        """Create a sample IronicProvisionSetEvent."""
        return IronicProvisionSetEvent(
            owner=uuid.uuid4(),
            lessee=uuid.uuid4(),
            instance_uuid=uuid.uuid4(),
            node_uuid=uuid.uuid4(),
            event="provision_end",
        )

    def test_create_volume_connector_success(self, mock_conn, sample_event):
        """Test successful volume connector creation."""
        mock_connector = MagicMock()
        mock_conn.baremetal.create_volume_connector.return_value = mock_connector

        result = create_volume_connector(mock_conn, sample_event)

        assert result == mock_connector
        expected_nqn = f"nqn.2014-08.org.nvmexpress:uuid:{sample_event.instance_uuid}"
        mock_conn.baremetal.create_volume_connector.assert_called_once_with(
            node_uuid=sample_event.node_uuid,
            type="iqn",
            connector_id=expected_nqn,
        )

    def test_create_volume_connector_with_different_instance_uuid(
        self, mock_conn, sample_event
    ):
        """Test volume connector creation with different instance UUID."""
        different_instance_uuid = uuid.uuid4()
        sample_event.instance_uuid = different_instance_uuid

        mock_connector = MagicMock()
        mock_conn.baremetal.create_volume_connector.return_value = mock_connector

        result = create_volume_connector(mock_conn, sample_event)

        assert result == mock_connector
        expected_nqn = f"nqn.2014-08.org.nvmexpress:uuid:{different_instance_uuid}"
        mock_conn.baremetal.create_volume_connector.assert_called_once_with(
            node_uuid=sample_event.node_uuid,
            type="iqn",
            connector_id=expected_nqn,
        )

    def test_create_volume_connector_baremetal_exception(self, mock_conn, sample_event):
        """Test handling when baremetal connector creation fails."""
        mock_conn.baremetal.create_volume_connector.side_effect = Exception(
            "Baremetal service error"
        )

        with pytest.raises(Exception, match="Baremetal service error"):
            create_volume_connector(mock_conn, sample_event)

        mock_conn.baremetal.create_volume_connector.assert_called_once()


class TestInstanceNqn:
    """Test cases for instance_nqn function."""

    def test_instance_nqn_format(self):
        """Test NQN format generation."""
        test_uuid = uuid.uuid4()
        expected_nqn = f"nqn.2014-08.org.nvmexpress:uuid:{test_uuid}"

        result = instance_nqn(test_uuid)

        assert result == expected_nqn

    def test_instance_nqn_different_uuids(self):
        """Test NQN generation with different UUIDs."""
        uuid1 = uuid.uuid4()
        uuid2 = uuid.uuid4()

        nqn1 = instance_nqn(uuid1)
        nqn2 = instance_nqn(uuid2)

        assert nqn1 != nqn2
        assert nqn1 == f"nqn.2014-08.org.nvmexpress:uuid:{uuid1}"
        assert nqn2 == f"nqn.2014-08.org.nvmexpress:uuid:{uuid2}"

    def test_instance_nqn_prefix_constant(self):
        """Test that NQN prefix is consistent."""
        test_uuid = uuid.uuid4()
        result = instance_nqn(test_uuid)

        assert result.startswith("nqn.2014-08.org.nvmexpress:uuid:")
        assert str(test_uuid) in result

    def test_instance_nqn_with_known_uuid(self):
        """Test NQN generation with a known UUID string."""
        known_uuid_str = "12345678-1234-5678-9abc-123456789abc"
        known_uuid = uuid.UUID(known_uuid_str)
        expected_nqn = f"nqn.2014-08.org.nvmexpress:uuid:{known_uuid_str}"

        result = instance_nqn(known_uuid)

        assert result == expected_nqn


@pytest.fixture
def ironic_inspection_data():
    """Load Ironic inspection inventory data from JSON fixture."""
    return _sample_fixture_data("ironic-inspect-inventory-node-data")


class TestIronicInspectionData:
    """Test cases for processing Ironic inspection data."""

    def test_chassis_info_from_inspection_data(self, ironic_inspection_data):
        """Test creating ChassisInfo from ironic-inspect-inventory-node-data.json."""
        # Import the function to convert inspection data to ChassisInfo
        from understack_workflows.ironic.inventory import get_device_info

        # Create ChassisInfo from inspection data
        chassis_info = get_device_info(ironic_inspection_data)

        # Assert basic chassis information
        assert chassis_info.manufacturer == "Dell Inc."
        assert chassis_info.model_number == "PowerEdge R7615"
        assert chassis_info.serial_number == "F3GSW04"
        assert chassis_info.bmc_ip_address == "10.46.96.165"
        assert chassis_info.bios_version == "1.6.10"
        assert chassis_info.power_on is True
        assert chassis_info.memory_gib == 96
        assert chassis_info.cpu == "AMD EPYC 9124 16-Core Processor"

        # Assert BMC interface
        assert chassis_info.bmc_interface.name == "iDRAC"
        assert chassis_info.bmc_interface.mac_address == "A8:3C:A5:35:41:3A"
        assert chassis_info.bmc_interface.hostname == "debian"
        assert str(chassis_info.bmc_interface.ipv4_address) == "10.46.96.165/26"

        # Assert we have the expected number of interfaces (1 BMC + 6 server interfaces)
        assert len(chassis_info.interfaces) == 7

        # Assert specific server interface details
        server_interfaces = [
            iface for iface in chassis_info.interfaces if iface.name != "iDRAC"
        ]

        # Check that we have interfaces with LLDP data
        interfaces_with_lldp = [
            iface
            for iface in server_interfaces
            if iface.remote_switch_mac_address is not None
        ]
        assert (
            len(interfaces_with_lldp) == 3
        )  # eno3np0, eno4np1, ens2f1np1 have LLDP data

        # Verify one specific interface with LLDP data (eno3np0 -> NIC.Integrated.1-1)
        eno3np0 = next(
            (
                iface
                for iface in chassis_info.interfaces
                if iface.name == "NIC.Integrated.1-1"
            ),
            None,
        )
        assert eno3np0 is not None
        assert eno3np0.mac_address == "D4:04:E6:4F:71:28"
        assert eno3np0.remote_switch_mac_address == "C4:7E:E0:E4:55:3F"
        assert eno3np0.remote_switch_port_name == "Ethernet1/4"

        # Verify neighbors (unique switch MAC addresses)
        assert len(chassis_info.neighbors) == 3
        assert "C4:7E:E0:E4:55:3F" in chassis_info.neighbors
        assert "40:14:82:81:3E:E3" in chassis_info.neighbors
        assert "C4:7E:E0:E7:A0:37" in chassis_info.neighbors
