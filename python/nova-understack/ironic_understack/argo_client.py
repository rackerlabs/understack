import time

import requests


class ArgoClient:
    """Client for interacting with Argo Workflows REST API."""

    def __init__(self, url: str, token: str, namespace="argo-events"):
        """Initialize the Argo client.

        Args:
            url: Base URL of the Argo Workflows server
            token: Authentication token for API access
        """
        self.url = url.rstrip("/")
        self.token = token
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        self.namespace = namespace

    def run_playbook(self, playbook_name: str, project_id: str, device_id: str) -> dict:
        """Run an Ansible playbook via Argo Workflows.

        This method creates a workflow from the ansible-workflow-template and waits
        for it to complete synchronously.

        Args:
            playbook_name: Name of the Ansible playbook to run
            project_id: Project ID parameter for the playbook
            device_id: Device ID parameter for the playbook
            env: Environment parameter (dev, staging, prod)

        Returns:
            dict: The final workflow status

        Raises:
            requests.RequestException: If API requests fail
            RuntimeError: If workflow fails or times out
        """
        # Create workflow from template
        workflow_request = {
            "workflow": {
                "metadata": {"generateName": "ansible-on-server-create-"},
                "spec": {
                    "workflowTemplateRef": {"name": "ansible-workflow-template"},
                    "entrypoint": "ansible-run",
                    "arguments": {
                        "parameters": [
                            {"name": "playbook", "value": playbook_name},
                            {
                                "name": "extra_vars",
                                "value": (
                                    f"project_id={project_id}"
                                    f" device_id={device_id}",
                                ),
                            },
                        ]
                    },
                },
            }
        }

        # Submit workflow
        response = self.session.post(
            f"{self.url}/api/v1/workflows/{self.namespace}", json=workflow_request
        )
        response.raise_for_status()

        workflow = response.json()
        workflow_name = workflow["metadata"]["name"]

        # Wait for workflow completion
        return self._wait_for_completion(workflow_name)

    def _wait_for_completion(
        self, workflow_name: str, timeout: int = 600, poll_interval: int = 5
    ) -> dict:
        """Wait for workflow to complete.

        Args:
            workflow_name: Name of the workflow to monitor
            timeout: Maximum time to wait in seconds (default: 10 minutes)
            poll_interval: Time between status checks in seconds

        Returns:
            dict: Final workflow status

        Raises:
            RuntimeError: If workflow fails or times out
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            response = self.session.get(
                f"{self.url}/api/v1/workflows/{self.namespace}/{workflow_name}"
            )
            response.raise_for_status()

            workflow = response.json()
            phase = workflow.get("status", {}).get("phase")

            if phase == "Succeeded":
                return workflow
            elif phase == "Failed":
                status = workflow.get("status", {}).get("message", "Unknown error")
                raise RuntimeError(f"Workflow {workflow_name} failed: {status}")
            elif phase == "Error":
                status = workflow.get("status", {}).get("message", "Unknown error")
                raise RuntimeError(
                    f"Workflow {workflow_name} encountered an error: {status}"
                )

            time.sleep(poll_interval)

        raise RuntimeError(
            f"Workflow {workflow_name} timed out after {timeout} seconds"
        )
