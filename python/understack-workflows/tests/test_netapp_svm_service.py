"""Tests for NetApp SVM Service."""

from unittest.mock import Mock

import pytest

from understack_workflows.netapp.exceptions import SvmOperationError
from understack_workflows.netapp.svm_service import SvmService
from understack_workflows.netapp.value_objects import SvmResult
from understack_workflows.netapp.value_objects import SvmSpec


class TestSvmService:
    """Test cases for SvmService class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock NetApp client."""
        return Mock()

    @pytest.fixture
    def svm_service(self, mock_client):
        """Create SvmService instance with mocked dependencies."""
        return SvmService(mock_client)

    def test_get_svm_name(self, svm_service):
        """Test SVM name generation follows naming convention."""
        project_id = "6c2fb34446bf4b35b4f1512e51f2303d"
        expected_name = "os-6c2fb34446bf4b35b4f1512e51f2303d"

        result = svm_service.get_svm_name(project_id)

        assert result == expected_name

    def test_create_svm_success(self, svm_service, mock_client):
        """Test successful SVM creation."""
        project_id = "test-project-123"
        aggregate_name = "test-aggregate"
        expected_svm_name = "os-test-project-123"

        # Mock client responses
        mock_client.find_svm.return_value = None  # SVM doesn't exist
        mock_client.create_svm.return_value = SvmResult(
            name=expected_svm_name, uuid="svm-uuid-123", state="online"
        )

        result = svm_service.create_svm(project_id, aggregate_name)

        assert result == expected_svm_name

        # Verify client was called with correct specification
        mock_client.create_svm.assert_called_once()
        call_args = mock_client.create_svm.call_args[0][0]
        assert isinstance(call_args, SvmSpec)
        assert call_args.name == expected_svm_name
        assert call_args.aggregate_name == aggregate_name
        assert call_args.language == "c.utf_8"
        assert call_args.allowed_protocols == ["nvme"]

    def test_create_svm_already_exists(self, svm_service, mock_client):
        """Test SVM creation when SVM already exists."""
        project_id = "test-project-123"
        aggregate_name = "test-aggregate"
        expected_svm_name = "os-test-project-123"

        # Mock SVM already exists
        mock_client.find_svm.return_value = SvmResult(
            name=expected_svm_name, uuid="existing-uuid", state="online"
        )

        with pytest.raises(SvmOperationError) as exc_info:
            svm_service.create_svm(project_id, aggregate_name)

        assert expected_svm_name in str(exc_info.value)
        assert project_id in str(exc_info.value)

        # Verify client create was not called
        mock_client.create_svm.assert_not_called()

    def test_create_svm_client_error(self, svm_service, mock_client):
        """Test SVM creation when client raises an error."""
        project_id = "test-project-123"
        aggregate_name = "test-aggregate"

        # Mock client responses
        mock_client.find_svm.return_value = None  # SVM doesn't exist
        mock_client.create_svm.side_effect = Exception("NetApp error")

        with pytest.raises(SvmOperationError) as exc_info:
            svm_service.create_svm(project_id, aggregate_name)

        assert "SVM creation for project" in str(exc_info.value)
        assert exc_info.value.svm_name == "os-test-project-123"
        assert exc_info.value.__cause__ is not None

    def test_delete_svm_success(self, svm_service, mock_client):
        """Test successful SVM deletion."""
        project_id = "test-project-123"
        expected_svm_name = "os-test-project-123"

        mock_client.delete_svm.return_value = True

        result = svm_service.delete_svm(project_id)

        assert result is True
        mock_client.delete_svm.assert_called_once_with(expected_svm_name)

    def test_delete_svm_failure(self, svm_service, mock_client):
        """Test SVM deletion failure."""
        project_id = "test-project-123"
        expected_svm_name = "os-test-project-123"

        mock_client.delete_svm.return_value = False

        result = svm_service.delete_svm(project_id)

        assert result is False
        mock_client.delete_svm.assert_called_once_with(expected_svm_name)

    def test_delete_svm_exception(self, svm_service, mock_client):
        """Test SVM deletion when client raises an exception."""
        project_id = "test-project-123"
        expected_svm_name = "os-test-project-123"

        mock_client.delete_svm.side_effect = Exception("NetApp error")

        result = svm_service.delete_svm(project_id)

        assert result is False
        mock_client.delete_svm.assert_called_once_with(expected_svm_name)

    def test_exists_true(self, svm_service, mock_client):
        """Test SVM existence check when SVM exists."""
        project_id = "test-project-123"
        expected_svm_name = "os-test-project-123"

        mock_client.find_svm.return_value = SvmResult(
            name=expected_svm_name, uuid="svm-uuid-123", state="online"
        )

        result = svm_service.exists(project_id)

        assert result is True
        mock_client.find_svm.assert_called_once_with(expected_svm_name)

    def test_exists_false(self, svm_service, mock_client):
        """Test SVM existence check when SVM doesn't exist."""
        project_id = "test-project-123"
        expected_svm_name = "os-test-project-123"

        mock_client.find_svm.return_value = None

        result = svm_service.exists(project_id)

        assert result is False
        mock_client.find_svm.assert_called_once_with(expected_svm_name)

    def test_exists_exception(self, svm_service, mock_client):
        """Test SVM existence check when client raises an exception."""
        project_id = "test-project-123"
        expected_svm_name = "os-test-project-123"

        mock_client.find_svm.side_effect = Exception("NetApp error")

        result = svm_service.exists(project_id)

        assert result is False
        mock_client.find_svm.assert_called_once_with(expected_svm_name)

    def test_get_svm_result_success(self, svm_service, mock_client):
        """Test getting SVM result when SVM exists."""
        project_id = "test-project-123"
        expected_svm_name = "os-test-project-123"
        expected_result = SvmResult(
            name=expected_svm_name, uuid="svm-uuid-123", state="online"
        )

        mock_client.find_svm.return_value = expected_result

        result = svm_service.get_svm_result(project_id)

        assert result == expected_result
        mock_client.find_svm.assert_called_once_with(expected_svm_name)

    def test_get_svm_result_not_found(self, svm_service, mock_client):
        """Test getting SVM result when SVM doesn't exist."""
        project_id = "test-project-123"
        expected_svm_name = "os-test-project-123"

        mock_client.find_svm.return_value = None

        result = svm_service.get_svm_result(project_id)

        assert result is None
        mock_client.find_svm.assert_called_once_with(expected_svm_name)

    def test_get_svm_result_exception(self, svm_service, mock_client):
        """Test getting SVM result when client raises an exception."""
        project_id = "test-project-123"
        expected_svm_name = "os-test-project-123"

        mock_client.find_svm.side_effect = Exception("NetApp error")

        result = svm_service.get_svm_result(project_id)

        assert result is None
        mock_client.find_svm.assert_called_once_with(expected_svm_name)

    def test_naming_convention_consistency(self, svm_service):
        """Test that naming convention is consistent across methods."""
        project_id = "test-project-456"
        expected_name = "os-test-project-456"

        # Test that get_svm_name returns the expected format
        name = svm_service.get_svm_name(project_id)
        assert name == expected_name

        # Test that the name follows the os-{project_id} pattern
        assert name.startswith("os-")
        assert name.endswith(project_id)

    def test_business_rules_in_svm_spec(self, svm_service, mock_client):
        """Test that business rules are properly applied in SVM specification."""
        project_id = "test-project-789"
        aggregate_name = "test-aggregate"

        # Mock client responses
        mock_client.find_svm.return_value = None
        mock_client.create_svm.return_value = SvmResult(
            name="os-test-project-789", uuid="uuid-123", state="online"
        )

        svm_service.create_svm(project_id, aggregate_name)

        # Verify the SVM spec follows business rules
        call_args = mock_client.create_svm.call_args[0][0]
        assert call_args.language == "c.utf_8"  # Business rule: always use UTF-8
        assert call_args.allowed_protocols == ["nvme"]  # Business rule: only NVMe
        assert call_args.name.startswith("os-")  # Business rule: naming convention
