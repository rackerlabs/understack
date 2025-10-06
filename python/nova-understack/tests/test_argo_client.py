"""Unit tests for ArgoClient."""

from unittest.mock import Mock
from unittest.mock import mock_open
from unittest.mock import patch

import pytest
import requests

from ironic_understack.argo_client import ArgoClient


class TestArgoClient:
    """Test cases for ArgoClient class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.base_url = "https://argo.example.com"
        self.token = "test-token"
        self.namespace = "test-namespace"

    @patch("ironic_understack.argo_client.urllib3.disable_warnings")
    def test_init_with_token(self, mock_disable_warnings):
        """Test ArgoClient initialization with provided token."""
        client = ArgoClient(
            url=self.base_url,
            token=self.token,
            namespace=self.namespace,
            ssl_verify=False,
        )

        assert client.url == self.base_url
        assert client.token == self.token
        assert client.namespace == self.namespace
        assert not client.session.verify
        assert client.session.headers["Authorization"] == f"Bearer {self.token}"
        assert client.session.headers["Content-Type"] == "application/json"
        mock_disable_warnings.assert_called_once()

    @patch("builtins.open", mock_open(read_data="k8s-token"))
    @patch("ironic_understack.argo_client.urllib3.disable_warnings")
    def test_init_without_token(self, mock_disable_warnings):
        """Test ArgoClient initialization without token (uses k8s token)."""
        client = ArgoClient(
            url=self.base_url, token=None, namespace=self.namespace, ssl_verify=False
        )

        assert client.token == "k8s-token"
        assert client.session.headers["Authorization"] == "Bearer k8s-token"

    def test_init_with_ssl_verify(self):
        """Test ArgoClient initialization with SSL verification enabled."""
        client = ArgoClient(url=self.base_url, token=self.token, ssl_verify=True)

        assert client.session.verify is True

    def test_url_stripping(self):
        """Test that trailing slashes are stripped from URL."""
        client = ArgoClient(url="https://argo.example.com/", token=self.token)

        assert client.url == "https://argo.example.com"

    def test_generate_workflow_name(self):
        """Test workflow name generation from playbook names."""
        client = ArgoClient(self.base_url, self.token)

        # Test with .yml extension
        result = client._generate_workflow_name("storage_on_server_create.yml")
        assert result == "ansible-storage-on-server-create-"

        # Test with .yaml extension
        result = client._generate_workflow_name("network_setup.yaml")
        assert result == "ansible-network-setup-"

        # Test without extension
        result = client._generate_workflow_name("deploy_app")
        assert result == "ansible-deploy-app-"

        # Test underscore replacement
        result = client._generate_workflow_name("test_playbook_name")
        assert result == "ansible-test-playbook-name-"

    @patch("builtins.open", mock_open(read_data="k8s-service-token"))
    def test_kubernetes_token_property(self):
        """Test reading Kubernetes service account token."""
        client = ArgoClient(self.base_url, None)

        token = client._kubernetes_token
        assert token == "k8s-service-token"

    @patch("requests.Session.post")
    @patch("requests.Session.get")
    def test_run_playbook_success(self, mock_get, mock_post):
        """Test successful playbook execution."""
        client = ArgoClient(self.base_url, self.token)

        # Mock workflow creation response
        workflow_response = {"metadata": {"name": "ansible-test-playbook-abc123"}}
        mock_post.return_value.json.return_value = workflow_response
        mock_post.return_value.raise_for_status = Mock()

        # Mock workflow completion response
        completed_workflow = {
            "status": {"phase": "Succeeded"},
            "metadata": {"name": "ansible-test-playbook-abc123"},
        }
        mock_get.return_value.json.return_value = completed_workflow
        mock_get.return_value.raise_for_status = Mock()

        result = client.run_playbook(
            "test_playbook.yml", device_id="device-123", project_id="project-456"
        )

        # Verify workflow creation request
        expected_workflow_request = {
            "workflow": {
                "metadata": {"generateName": "ansible-test-playbook-"},
                "spec": {
                    "workflowTemplateRef": {"name": "ansible-workflow-template"},
                    "entrypoint": "ansible-run",
                    "arguments": {
                        "parameters": [
                            {"name": "playbook", "value": "test_playbook.yml"},
                            {
                                "name": "extra_vars",
                                "value": "device_id=device-123 project_id=project-456",
                            },
                        ]
                    },
                },
            }
        }

        mock_post.assert_called_once_with(
            f"{self.base_url}/api/v1/workflows/{client.namespace}",
            json=expected_workflow_request,
        )

        # Verify workflow monitoring
        mock_get.assert_called_with(
            f"{self.base_url}/api/v1/workflows/{client.namespace}/ansible-test-playbook-abc123"
        )

        assert result == completed_workflow

    @patch("requests.Session.post")
    def test_run_playbook_creation_failure(self, mock_post):
        """Test playbook execution when workflow creation fails."""
        client = ArgoClient(self.base_url, self.token)

        mock_post.return_value.raise_for_status.side_effect = requests.RequestException(
            "API Error"
        )

        with pytest.raises(requests.RequestException):
            client.run_playbook("test_playbook.yml")

    @patch("requests.Session.post")
    @patch("requests.Session.get")
    def test_run_playbook_with_empty_extra_vars(self, mock_get, mock_post):
        """Test playbook execution with no extra variables."""
        client = ArgoClient(self.base_url, self.token)

        workflow_response = {"metadata": {"name": "ansible-test-abc123"}}
        mock_post.return_value.json.return_value = workflow_response
        mock_post.return_value.raise_for_status = Mock()

        completed_workflow = {"status": {"phase": "Succeeded"}}
        mock_get.return_value.json.return_value = completed_workflow
        mock_get.return_value.raise_for_status = Mock()

        client.run_playbook("test_playbook.yml")

        # Verify empty extra_vars string
        call_args = mock_post.call_args[1]["json"]
        extra_vars_param = call_args["workflow"]["spec"]["arguments"]["parameters"][1]
        assert extra_vars_param["value"] == ""

    @patch("time.sleep")
    @patch("requests.Session.get")
    def test_wait_for_completion_success(self, mock_get, mock_sleep):
        """Test successful workflow completion monitoring."""
        client = ArgoClient(self.base_url, self.token)

        # Mock workflow status progression
        responses = [
            {"status": {"phase": "Running"}},
            {"status": {"phase": "Running"}},
            {"status": {"phase": "Succeeded"}},
        ]
        mock_get.return_value.json.side_effect = responses
        mock_get.return_value.raise_for_status = Mock()

        result = client._wait_for_completion("test-workflow")

        assert result == responses[-1]
        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("time.sleep")
    @patch("requests.Session.get")
    def test_wait_for_completion_failure(self, mock_get, mock_sleep):
        """Test workflow failure during monitoring."""
        client = ArgoClient(self.base_url, self.token)

        failed_workflow = {
            "status": {"phase": "Failed", "message": "Workflow execution failed"}
        }
        mock_get.return_value.json.return_value = failed_workflow
        mock_get.return_value.raise_for_status = Mock()

        with pytest.raises(RuntimeError, match="Workflow test-workflow failed"):
            client._wait_for_completion("test-workflow")

    @patch("time.sleep")
    @patch("requests.Session.get")
    def test_wait_for_completion_error(self, mock_get, mock_sleep):
        """Test workflow error during monitoring."""
        client = ArgoClient(self.base_url, self.token)

        error_workflow = {
            "status": {"phase": "Error", "message": "Workflow encountered an error"}
        }
        mock_get.return_value.json.return_value = error_workflow
        mock_get.return_value.raise_for_status = Mock()

        with pytest.raises(
            RuntimeError, match="Workflow test-workflow encountered an error"
        ):
            client._wait_for_completion("test-workflow")

    @patch("time.time")
    @patch("time.sleep")
    @patch("requests.Session.get")
    def test_wait_for_completion_timeout(self, mock_get, mock_sleep, mock_time):
        """Test workflow timeout during monitoring."""
        client = ArgoClient(self.base_url, self.token)

        # Mock time progression to simulate timeout
        mock_time.side_effect = [0, 300, 700]  # Start, middle, timeout

        running_workflow = {"status": {"phase": "Running"}}
        mock_get.return_value.json.return_value = running_workflow
        mock_get.return_value.raise_for_status = Mock()

        with pytest.raises(RuntimeError, match="Workflow test-workflow timed out"):
            client._wait_for_completion("test-workflow", timeout=600)

    @patch("requests.Session.get")
    def test_wait_for_completion_api_error(self, mock_get):
        """Test API error during workflow monitoring."""
        client = ArgoClient(self.base_url, self.token)

        mock_get.return_value.raise_for_status.side_effect = requests.RequestException(
            "API Error"
        )

        with pytest.raises(requests.RequestException):
            client._wait_for_completion("test-workflow")

    @patch("time.sleep")
    @patch("requests.Session.get")
    def test_wait_for_completion_missing_status(self, mock_get, mock_sleep):
        """Test workflow monitoring with missing status information."""
        client = ArgoClient(self.base_url, self.token)

        # Mock workflow without status
        workflow_no_status = {"metadata": {"name": "test-workflow"}}
        mock_get.return_value.json.return_value = workflow_no_status
        mock_get.return_value.raise_for_status = Mock()

        # Should continue polling when status is missing
        with patch("time.time", side_effect=[0, 700]):  # Simulate timeout
            with pytest.raises(RuntimeError, match="timed out"):
                client._wait_for_completion(
                    "test-workflow", timeout=600, poll_interval=1
                )
