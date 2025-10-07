"""Unit tests for IronicUnderstackDriver."""

from unittest.mock import Mock
from unittest.mock import patch
from uuid import UUID
from uuid import uuid4

import pytest


class TestIronicUnderstackDriver:
    """Test cases for IronicUnderstackDriver class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.virtapi = Mock()

        # Mock the configuration
        self.mock_conf = Mock()
        self.mock_conf.nova_understack.nautobot_base_url = (
            "https://nautobot.example.com"
        )
        self.mock_conf.nova_understack.nautobot_api_key = "test-api-key"
        self.mock_conf.nova_understack.argo_api_url = "https://argo.example.com"
        self.mock_conf.nova_understack.ip_injection_enabled = True
        self.mock_conf.nova_understack.ansible_playbook_filename = (
            "storage_on_server_create.yml"
        )

    @patch("ironic_understack.driver.CONF")
    @patch("ironic_understack.driver.ArgoClient")
    @patch("ironic_understack.driver.NautobotClient")
    @patch("nova.virt.ironic.driver.IronicDriver.__init__")
    def test_init(
        self, mock_super_init, mock_nautobot_client, mock_argo_client, mock_conf
    ):
        """Test driver initialization."""
        mock_conf.nova_understack = self.mock_conf.nova_understack
        mock_super_init.return_value = None

        # Import here to avoid Nova import issues during module loading
        from ironic_understack.driver import IronicUnderstackDriver

        driver = IronicUnderstackDriver(self.virtapi, read_only=False)

        # Verify clients are initialized with correct parameters
        mock_nautobot_client.assert_called_once_with(
            "https://nautobot.example.com", "test-api-key"
        )
        mock_argo_client.assert_called_once_with("https://argo.example.com", None)

        assert driver._nautobot_connection == mock_nautobot_client.return_value
        assert driver._argo_connection == mock_argo_client.return_value
        mock_super_init.assert_called_once_with(self.virtapi, False)

    @patch("ironic_understack.driver.CONF")
    @patch("ironic_understack.driver.ArgoClient")
    @patch("ironic_understack.driver.NautobotClient")
    @patch("nova.virt.ironic.driver.IronicDriver.__init__")
    def test_understack_get_network_metadata_with_storage_wanted(
        self, mock_super_init, mock_nautobot_client, mock_argo_client, mock_conf
    ):
        """Test _understack_get_network_metadata with storage=wanted."""
        mock_conf.nova_understack = self.mock_conf.nova_understack
        mock_super_init.return_value = None

        from ironic_understack.driver import IronicUnderstackDriver

        driver = IronicUnderstackDriver(self.virtapi)

        # Mock instance with storage metadata
        instance = Mock()
        instance.metadata = {"storage": "wanted"}
        instance.uuid = str(uuid4())
        instance.project_id = str(uuid4())

        # Mock node
        node = {"uuid": str(uuid4())}

        # Mock network_info
        network_info = Mock()

        # Mock argo client response
        argo_result = {"status": {"phase": "Succeeded"}}
        driver._argo_connection.run_playbook.return_value = argo_result

        # Mock network metadata
        expected_metadata = {"test": "storage_metadata"}

        # Mock the _get_network_metadata_with_storage method
        with patch.object(
            driver, "_get_network_metadata_with_storage", return_value=expected_metadata
        ):
            result = driver._understack_get_network_metadata(
                instance, node, network_info
            )

            # Verify argo client was called with correct parameters
            expected_playbook_args = {
                "device_id": node["uuid"],
                "project_id": str(UUID(instance.project_id)),
            }
            driver._argo_connection.run_playbook.assert_called_once_with(
                "storage_on_server_create.yml", **expected_playbook_args
            )

            # Verify network metadata was retrieved with storage
            driver._get_network_metadata_with_storage.assert_called_once_with(
                node, network_info
            )

            assert result == expected_metadata

    @patch("ironic_understack.driver.CONF")
    @patch("ironic_understack.driver.ArgoClient")
    @patch("ironic_understack.driver.NautobotClient")
    @patch("nova.virt.ironic.driver.IronicDriver.__init__")
    @patch("nova.virt.ironic.driver.IronicDriver._get_network_metadata")
    def test_understack_get_network_metadata_without_storage(
        self,
        mock_parent_get_metadata,
        mock_super_init,
        mock_nautobot_client,
        mock_argo_client,
        mock_conf,
    ):
        """Test _understack_get_network_metadata without storage requirement."""
        mock_conf.nova_understack = self.mock_conf.nova_understack
        mock_super_init.return_value = None

        from ironic_understack.driver import IronicUnderstackDriver

        driver = IronicUnderstackDriver(self.virtapi)

        # Mock instance without storage metadata
        instance = Mock()
        instance.metadata = {"storage": "not-wanted"}
        instance.uuid = str(uuid4())

        # Mock node
        node = {"uuid": str(uuid4())}

        # Mock network_info
        network_info = Mock()

        # Mock network metadata
        expected_metadata = {"test": "standard_metadata"}
        mock_parent_get_metadata.return_value = expected_metadata

        result = driver._understack_get_network_metadata(instance, node, network_info)

        # Verify argo client was NOT called
        driver._argo_connection.run_playbook.assert_not_called()

        # Verify standard network metadata was retrieved
        mock_parent_get_metadata.assert_called_once_with(node, network_info)

        assert result == expected_metadata

    @patch("ironic_understack.driver.CONF")
    @patch("ironic_understack.driver.ArgoClient")
    @patch("ironic_understack.driver.NautobotClient")
    @patch("nova.virt.ironic.driver.IronicDriver.__init__")
    @patch("nova.virt.ironic.driver.IronicDriver._get_network_metadata")
    def test_understack_get_network_metadata_ip_injection_disabled(
        self,
        mock_parent_get_metadata,
        mock_super_init,
        mock_nautobot_client,
        mock_argo_client,
        mock_conf,
    ):
        """Test _understack_get_network_metadata with IP injection disabled."""
        # Disable IP injection
        self.mock_conf.nova_understack.ip_injection_enabled = False
        mock_conf.nova_understack = self.mock_conf.nova_understack
        mock_super_init.return_value = None

        from ironic_understack.driver import IronicUnderstackDriver

        driver = IronicUnderstackDriver(self.virtapi)

        # Mock instance with storage metadata
        instance = Mock()
        instance.metadata = {"storage": "wanted"}
        instance.uuid = str(uuid4())

        # Mock node
        node = {"uuid": str(uuid4())}

        # Mock network_info
        network_info = Mock()

        # Mock network metadata
        expected_metadata = {"test": "standard_metadata"}
        mock_parent_get_metadata.return_value = expected_metadata

        result = driver._understack_get_network_metadata(instance, node, network_info)

        # Verify argo client was NOT called even though storage is wanted
        driver._argo_connection.run_playbook.assert_not_called()

        # Verify standard network metadata was retrieved
        mock_parent_get_metadata.assert_called_once_with(node, network_info)

        assert result == expected_metadata

    @patch("ironic_understack.driver.CONF")
    @patch("ironic_understack.driver.ArgoClient")
    @patch("ironic_understack.driver.NautobotClient")
    @patch("nova.virt.ironic.driver.IronicDriver.__init__")
    @patch("nova.virt.ironic.driver.IronicDriver._get_network_metadata")
    def test_understack_get_network_metadata_missing_storage_key(
        self,
        mock_parent_get_metadata,
        mock_super_init,
        mock_nautobot_client,
        mock_argo_client,
        mock_conf,
    ):
        """Test when storage key is missing from metadata."""
        mock_conf.nova_understack = self.mock_conf.nova_understack
        mock_super_init.return_value = None

        from ironic_understack.driver import IronicUnderstackDriver

        driver = IronicUnderstackDriver(self.virtapi)

        # Mock instance without storage key in metadata
        instance = Mock()
        instance.metadata = {"other_key": "value"}
        instance.uuid = str(uuid4())

        # Mock node
        node = {"uuid": str(uuid4())}

        # Mock network_info
        network_info = Mock()

        # Mock network metadata
        expected_metadata = {"test": "standard_metadata"}
        mock_parent_get_metadata.return_value = expected_metadata

        result = driver._understack_get_network_metadata(instance, node, network_info)

        # Verify argo client was NOT called
        driver._argo_connection.run_playbook.assert_not_called()

        # Verify standard network metadata was retrieved
        mock_parent_get_metadata.assert_called_once_with(node, network_info)

        assert result == expected_metadata

    @patch("ironic_understack.driver.CONF")
    @patch("ironic_understack.driver.ArgoClient")
    @patch("ironic_understack.driver.NautobotClient")
    @patch("nova.virt.ironic.driver.IronicDriver.__init__")
    def test_understack_get_network_metadata_argo_playbook_failure(
        self, mock_super_init, mock_nautobot_client, mock_argo_client, mock_conf
    ):
        """Test _understack_get_network_metadata when Argo playbook fails."""
        mock_conf.nova_understack = self.mock_conf.nova_understack
        mock_super_init.return_value = None

        from ironic_understack.driver import IronicUnderstackDriver

        driver = IronicUnderstackDriver(self.virtapi)

        # Mock instance with storage metadata
        instance = Mock()
        instance.metadata = {"storage": "wanted"}
        instance.uuid = str(uuid4())
        instance.project_id = str(uuid4())

        # Mock node
        node = {"uuid": str(uuid4())}

        # Mock network_info
        network_info = Mock()

        # Mock argo client to raise exception
        driver._argo_connection.run_playbook.side_effect = RuntimeError(
            "Playbook failed"
        )

        # Should propagate the exception
        with pytest.raises(RuntimeError, match="Playbook failed"):
            driver._understack_get_network_metadata(instance, node, network_info)

    @patch("ironic_understack.driver.CONF")
    @patch("ironic_understack.driver.ArgoClient")
    @patch("ironic_understack.driver.NautobotClient")
    @patch("nova.virt.ironic.driver.IronicDriver.__init__")
    def test_get_network_metadata_with_storage(
        self, mock_super_init, mock_nautobot_client, mock_argo_client, mock_conf
    ):
        """Test _get_network_metadata_with_storage method."""
        mock_conf.nova_understack = self.mock_conf.nova_understack
        mock_super_init.return_value = None

        from ironic_understack.driver import IronicUnderstackDriver

        driver = IronicUnderstackDriver(self.virtapi)

        # Mock the parent class method
        base_metadata = {
            "links": [{"id": "existing-link"}],
            "networks": [{"id": "existing-network"}],
        }

        with patch.object(
            driver.__class__.__bases__[0],
            "_get_network_metadata",
            return_value=base_metadata,
        ):
            # Mock nautobot client response
            extra_interfaces = {
                "links": [{"id": "storage-link"}],
                "networks": [{"id": "storage-network"}],
            }
            driver._nautobot_connection.storage_network_config_for_node.return_value = (
                extra_interfaces
            )

            node = {"uuid": str(uuid4())}
            network_info = Mock()

            result = driver._get_network_metadata_with_storage(node, network_info)

            # Verify nautobot client was called with correct UUID
            driver._nautobot_connection.storage_network_config_for_node.assert_called_once_with(
                UUID(node["uuid"])
            )

            # Verify metadata was merged correctly
            expected_result = {
                "links": [{"id": "existing-link"}, {"id": "storage-link"}],
                "networks": [{"id": "existing-network"}, {"id": "storage-network"}],
            }
            assert result == expected_result

    @patch("ironic_understack.driver.CONF")
    @patch("ironic_understack.driver.ArgoClient")
    @patch("ironic_understack.driver.NautobotClient")
    @patch("nova.virt.ironic.driver.IronicDriver.__init__")
    def test_get_network_metadata_with_storage_no_base_metadata(
        self, mock_super_init, mock_nautobot_client, mock_argo_client, mock_conf
    ):
        """Test _get_network_metadata_with_storage when base metadata is None."""
        mock_conf.nova_understack = self.mock_conf.nova_understack
        mock_super_init.return_value = None

        from ironic_understack.driver import IronicUnderstackDriver

        driver = IronicUnderstackDriver(self.virtapi)

        # Mock the parent class method to return None
        with patch.object(
            driver.__class__.__bases__[0], "_get_network_metadata", return_value=None
        ):
            node = {"uuid": str(uuid4())}
            network_info = Mock()

            result = driver._get_network_metadata_with_storage(node, network_info)

            # Should return None without calling nautobot
            assert result is None
            driver._nautobot_connection.storage_network_config_for_node.assert_not_called()
