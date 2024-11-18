import time

import requests
import urllib3

urllib3.disable_warnings()


DEFAULT_TOKEN_FILENAME = "/run/secrets/kubernetes.io/serviceaccount/token"  # noqa: S105


class ArgoClient:
    def __init__(
        self,
        token: str | None = None,
        namespace="default",
        api_url="https://argo-server.argo.svc.cluster.local:2746",
        logger=None,
    ):
        """Simple Argo Workflows Client."""
        if token is None:
            with open(DEFAULT_TOKEN_FILENAME) as token_file:
                token = token_file.read()
        self.token = token
        self.namespace = namespace
        self.api_url = api_url
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.logger = logger

    def submit(
        self,
        template_name: str,
        entrypoint: str,
        parameters: dict,
        service_account="default",
    ):
        json_body = self.__request_body(
            template_name, entrypoint, parameters, service_account
        )

        response = requests.post(
            f"{self.api_url}/api/v1/workflows/{self.namespace}/submit",
            headers=self.headers,
            json=json_body,
            verify=False,  # noqa: S501 we should revisit this
            timeout=30,
        )
        response.raise_for_status()
        if self.logger:
            self.logger.debug(f"Response: {response.json()}")
        return response

    def submit_wait(self, *args, **kwargs):
        max_attempts = kwargs.pop("max_attempts", 20)
        response = self.submit(*args, **kwargs)
        workflow_name = response.json()["metadata"]["name"]
        result = None
        for i in range(1, max_attempts + 1):
            if self.logger:
                self.logger.debug(f"Workflow: {workflow_name} retry {i}/{max_attempts}")
            time.sleep(5)
            result = self.check_status(workflow_name)
            if result in ["Succeeded", "Failed", "Error"]:
                break
        return result

    def check_status(self, name: str):
        response = requests.get(
            f"{self.api_url}/api/v1/workflows/{self.namespace}/{name}",
            headers=self.headers,
            json={"fields": "status.phase"},
            verify=False,  # noqa: S501 we should revisit this
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["status"]["phase"]

    def __request_body(
        self,
        template_name: str,
        entrypoint: str,
        parameters: dict,
        service_account: str,
    ):
        return {
            "resourceKind": "WorkflowTemplate",
            "namespace": self.namespace,
            "resourceName": template_name,
            "submitOptions": {
                "labels": f"workflows.argoproj.io/workflow-template={template_name}",
                "parameters": [f"{k}={v}" for k, v in parameters.items()],
                "entryPoint": entrypoint,
                "serviceAccount": service_account,
            },
        }
