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

    def _generate_workflow_name(self, playbook_name: str) -> str:
        """Generate workflow name based on playbook name.

        Strips .yaml/.yml suffix and creates ansible-<name>- format.

        Args:
            playbook_name: Name of the Ansible playbook

        Returns:
            str: Generated workflow name in format ansible-<name>-

        Examples:
            storage_on_server_create.yml -> ansible-storage_on_server_create-
            network_setup.yaml -> ansible-network_setup-
            deploy_app -> ansible-deploy_app-
        """
        base_name = playbook_name.replace("_", "-")
        if base_name.endswith((".yaml", ".yml")):
            base_name = base_name.rsplit(".", 1)[0]
        return f"ansible-{base_name}-"

    def run_playbook(self, playbook_name: str, **extra_vars) -> dict:
        """Run an Ansible playbook via Argo Workflows.

        This method creates a workflow from the ansible-workflow-template and waits
        for it to complete synchronously.

        Args:
            playbook_name: Name of the Ansible playbook to run
            **extra_vars: Arbitrary key/value pairs to pass as extra_vars to Ansible

        Returns:
            dict: The final workflow status

        Raises:
            requests.RequestException: If API requests fail
            RuntimeError: If workflow fails or times out
        """
        # Convert extra_vars dict to space-separated key=value string
        extra_vars_str = " ".join(f"{key}={value}" for key, value in extra_vars.items())

        # Generate workflow name based on playbook name
        generate_name = self._generate_workflow_name(playbook_name)

        # Create workflow from template
        workflow_request = {
            "workflow": {
                "metadata": {"generateName": generate_name},
                "spec": {
                    "workflowTemplateRef": {"name": "ansible-workflow-template"},
                    "entrypoint": "ansible-run",
                    "arguments": {
                        "parameters": [
                            {"name": "playbook", "value": playbook_name},
                            {
                                "name": "extra_vars",
                                "value": extra_vars_str,
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
