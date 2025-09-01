"""Tests for NetApp Volume Service."""

from unittest.mock import Mock

import pytest

from understack_workflows.netapp.exceptions import NetAppManagerError
from understack_workflows.netapp.value_objects import NamespaceResult
from understack_workflows.netapp.value_objects import NamespaceSpec
from understack_workflows.netapp.value_objects import VolumeResult
from understack_workflows.netapp.value_objects import VolumeSpec
from understack_workflows.netapp.volume_service import VolumeService


class TestVolumeService:
    """Test cases for VolumeService class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock NetApp client."""
        return Mock()

    @pytest.fixture
    def mock_error_handler(self):
        """Create a mock error handler."""
        return Mock()

    @pytest.fixture
    def volume_service(self, mock_client, mock_error_handler):
        """Create VolumeService instance with mocked dependencies."""
        return VolumeService(mock_client, mock_error_handler)

    def test_get_volume_name(self, volume_service):
        """Test volume name generation follows naming convention."""
        project_id = "6c2fb34446bf4b35b4f1512e51f2303d"
        expected_name = "vol_6c2fb34446bf4b35b4f1512e51f2303d"

        result = volume_service.get_volume_name(project_id)

        assert result == expected_name

    def test_create_volume_success(
        self, volume_service, mock_client, mock_error_handler
    ):
        """Test successful volume creation."""
        project_id = "test-project-123"
        size = "1TB"
        aggregate_name = "test-aggregate"
        expected_volume_name = "vol_test-project-123"
        expected_svm_name = "os-test-project-123"

        mock_client.create_volume.return_value = VolumeResult(
            name=expected_volume_name,
            uuid="volume-uuid-123",
            size=size,
            state="online",
            svm_name=expected_svm_name,
        )

        result = volume_service.create_volume(project_id, size, aggregate_name)

        assert result == expected_volume_name

        # Verify client was called with correct specification
        mock_client.create_volume.assert_called_once()
        call_args = mock_client.create_volume.call_args[0][0]
        assert isinstance(call_args, VolumeSpec)
        assert call_args.name == expected_volume_name
        assert call_args.svm_name == expected_svm_name
        assert call_args.aggregate_name == aggregate_name
        assert call_args.size == size

        # Verify logging
        mock_error_handler.log_info.assert_called()

    def test_create_volume_client_error(
        self, volume_service, mock_client, mock_error_handler
    ):
        """Test volume creation when client raises an error."""
        project_id = "test-project-123"
        size = "1TB"
        aggregate_name = "test-aggregate"

        mock_client.create_volume.side_effect = Exception("NetApp error")
        mock_error_handler.handle_operation_error.side_effect = NetAppManagerError(
            "Operation failed"
        )

        with pytest.raises(NetAppManagerError):
            volume_service.create_volume(project_id, size, aggregate_name)

        # Verify error handler was called
        mock_error_handler.handle_operation_error.assert_called_once()

    def test_delete_volume_success(
        self, volume_service, mock_client, mock_error_handler
    ):
        """Test successful volume deletion."""
        project_id = "test-project-123"
        expected_volume_name = "vol_test-project-123"

        mock_client.delete_volume.return_value = True

        result = volume_service.delete_volume(project_id)

        assert result is True
        mock_client.delete_volume.assert_called_once_with(expected_volume_name, False)
        mock_error_handler.log_info.assert_called()

    def test_delete_volume_with_force(
        self, volume_service, mock_client, mock_error_handler
    ):
        """Test volume deletion with force flag."""
        project_id = "test-project-123"
        expected_volume_name = "vol_test-project-123"

        mock_client.delete_volume.return_value = True

        result = volume_service.delete_volume(project_id, force=True)

        assert result is True
        mock_client.delete_volume.assert_called_once_with(expected_volume_name, True)
        mock_error_handler.log_info.assert_called()

    def test_delete_volume_failure(
        self, volume_service, mock_client, mock_error_handler
    ):
        """Test volume deletion failure."""
        project_id = "test-project-123"
        expected_volume_name = "vol_test-project-123"

        mock_client.delete_volume.return_value = False

        result = volume_service.delete_volume(project_id)

        assert result is False
        mock_client.delete_volume.assert_called_once_with(expected_volume_name, False)
        mock_error_handler.log_warning.assert_called()

    def test_delete_volume_exception(
        self, volume_service, mock_client, mock_error_handler
    ):
        """Test volume deletion when client raises an exception."""
        project_id = "test-project-123"
        expected_volume_name = "vol_test-project-123"

        mock_client.delete_volume.side_effect = Exception("NetApp error")

        result = volume_service.delete_volume(project_id)

        assert result is False
        mock_client.delete_volume.assert_called_once_with(expected_volume_name, False)
        mock_error_handler.log_warning.assert_called()

    def test_get_mapped_namespaces_success(
        self, volume_service, mock_client, mock_error_handler
    ):
        """Test successful namespace retrieval."""
        project_id = "test-project-123"
        expected_volume_name = "vol_test-project-123"
        expected_svm_name = "os-test-project-123"

        expected_namespaces = [
            NamespaceResult(
                uuid="ns-uuid-1",
                name="namespace-1",
                mapped=True,
                svm_name=expected_svm_name,
                volume_name=expected_volume_name,
            ),
            NamespaceResult(
                uuid="ns-uuid-2",
                name="namespace-2",
                mapped=False,
                svm_name=expected_svm_name,
                volume_name=expected_volume_name,
            ),
        ]

        mock_client.get_namespaces.return_value = expected_namespaces

        result = volume_service.get_mapped_namespaces(project_id)

        assert result == expected_namespaces

        # Verify client was called with correct specification
        mock_client.get_namespaces.assert_called_once()
        call_args = mock_client.get_namespaces.call_args[0][0]
        assert isinstance(call_args, NamespaceSpec)
        assert call_args.svm_name == expected_svm_name
        assert call_args.volume_name == expected_volume_name

        # Verify logging
        mock_error_handler.log_info.assert_called()

    def test_get_mapped_namespaces_empty(
        self, volume_service, mock_client, mock_error_handler
    ):
        """Test namespace retrieval when no namespaces exist."""
        project_id = "test-project-123"
        expected_volume_name = "vol_test-project-123"
        expected_svm_name = "os-test-project-123"

        mock_client.get_namespaces.return_value = []

        result = volume_service.get_mapped_namespaces(project_id)

        assert result == []

        # Verify client was called with correct specification
        mock_client.get_namespaces.assert_called_once()
        call_args = mock_client.get_namespaces.call_args[0][0]
        assert isinstance(call_args, NamespaceSpec)
        assert call_args.svm_name == expected_svm_name
        assert call_args.volume_name == expected_volume_name

    def test_get_mapped_namespaces_exception(
        self, volume_service, mock_client, mock_error_handler
    ):
        """Test namespace retrieval when client raises an exception."""
        project_id = "test-project-123"

        mock_client.get_namespaces.side_effect = Exception("NetApp error")

        result = volume_service.get_mapped_namespaces(project_id)

        assert result == []
        mock_client.get_namespaces.assert_called_once()
        mock_error_handler.log_warning.assert_called()

    def test_naming_convention_consistency(self, volume_service):
        """Test that naming convention is consistent across methods."""
        project_id = "test-project-456"
        expected_volume_name = "vol_test-project-456"
        expected_svm_name = "os-test-project-456"

        # Test that get_volume_name returns the expected format
        volume_name = volume_service.get_volume_name(project_id)
        assert volume_name == expected_volume_name

        # Test that the volume name follows the vol_{project_id} pattern
        assert volume_name.startswith("vol_")
        assert volume_name.endswith(project_id)

        # Test that SVM name follows the os-{project_id} pattern
        svm_name = volume_service._get_svm_name(project_id)
        assert svm_name == expected_svm_name
        assert svm_name.startswith("os-")
        assert svm_name.endswith(project_id)

    def test_volume_spec_creation(
        self, volume_service, mock_client, mock_error_handler
    ):
        """Test that volume specification is created correctly."""
        project_id = "test-project-789"
        size = "2TB"
        aggregate_name = "test-aggregate"

        mock_client.create_volume.return_value = VolumeResult(
            name="vol_test-project-789", uuid="uuid-123", size=size, state="online"
        )

        volume_service.create_volume(project_id, size, aggregate_name)

        # Verify the volume spec is created correctly
        call_args = mock_client.create_volume.call_args[0][0]
        assert call_args.name == "vol_test-project-789"
        assert call_args.svm_name == "os-test-project-789"
        assert call_args.aggregate_name == aggregate_name
        assert call_args.size == size

    def test_namespace_spec_creation(
        self, volume_service, mock_client, mock_error_handler
    ):
        """Test that namespace specification is created correctly."""
        project_id = "test-project-789"

        mock_client.get_namespaces.return_value = []

        volume_service.get_mapped_namespaces(project_id)

        # Verify the namespace spec is created correctly
        call_args = mock_client.get_namespaces.call_args[0][0]
        assert call_args.svm_name == "os-test-project-789"
        assert call_args.volume_name == "vol_test-project-789"

    def test_svm_name_consistency_with_svm_service(self, volume_service):
        """Test that SVM naming is consistent with SvmService."""
        project_id = "consistency-test-123"

        # The VolumeService should generate the same SVM name as SvmService
        svm_name = volume_service._get_svm_name(project_id)

        # This should match the naming convention from SvmService
        expected_svm_name = f"os-{project_id}"
        assert svm_name == expected_svm_name

    def test_exists_volume_found(self, volume_service, mock_client, mock_error_handler):
        """Test exists method when volume is found."""
        project_id = "test-project-123"
        expected_volume_name = "vol_test-project-123"
        expected_svm_name = "os-test-project-123"

        mock_volume_result = VolumeResult(
            name=expected_volume_name,
            uuid="volume-uuid-123",
            size="1TB",
            state="online",
            svm_name=expected_svm_name,
        )
        mock_client.find_volume.return_value = mock_volume_result

        result = volume_service.exists(project_id)

        assert result is True
        mock_client.find_volume.assert_called_once_with(
            expected_volume_name, expected_svm_name
        )
        mock_error_handler.log_debug.assert_called()

    def test_exists_volume_not_found(
        self, volume_service, mock_client, mock_error_handler
    ):
        """Test exists method when volume is not found."""
        project_id = "test-project-123"
        expected_volume_name = "vol_test-project-123"
        expected_svm_name = "os-test-project-123"

        mock_client.find_volume.return_value = None

        result = volume_service.exists(project_id)

        assert result is False
        mock_client.find_volume.assert_called_once_with(
            expected_volume_name, expected_svm_name
        )
        mock_error_handler.log_debug.assert_called()

    def test_exists_client_exception(
        self, volume_service, mock_client, mock_error_handler
    ):
        """Test exists method when client raises an exception."""
        project_id = "test-project-123"
        expected_volume_name = "vol_test-project-123"
        expected_svm_name = "os-test-project-123"

        mock_client.find_volume.side_effect = Exception("Connection error")

        result = volume_service.exists(project_id)

        assert result is False  # Should return False on error to avoid blocking cleanup
        mock_client.find_volume.assert_called_once_with(
            expected_volume_name, expected_svm_name
        )
        mock_error_handler.log_warning.assert_called()
