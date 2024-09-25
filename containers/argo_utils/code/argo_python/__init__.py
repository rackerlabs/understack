from kubernetes import client, config
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class ArgoWorkflow:
    def __init__(
        self,
        namespace: str,
        name: str,
        uid: str,
        api_version="argoproj.io/v1alpha1",
        config_file=None,
    ):
        if config_file:
            config.load_kube_config(config_file)
        else:
            config.load_incluster_config()

        self.kube = client.CoreV1Api()
        self.namespace = namespace
        self.name = name
        self.uid = uid
        self.api_version = api_version

    def get_pod(self, name):
        r = self.kube.read_namespaced_pod(name, self.namespace)
        return r.metadata

    def create_secret(self, name: str, data: Dict) -> str:
        """
        create_secret creates a kubernetes secret, setting ownerReferences to provide garbage collection.

        :param name: metadata.name of the kubernetes secret
        :param data: data dict to be stored in the secret
        :return: the name of the kubernetes secret
        """

        owner = client.V1OwnerReference(
            api_version=self.api_version,
            kind="Workflow",
            name=self.name,
            uid=self.uid,
            block_owner_deletion=True,
            controller=True,
        )

        meta = client.V1ObjectMeta(
            name=name,
            owner_references=[owner],
        )

        secret = client.V1Secret(
            api_version="v1",
            kind="Secret",
            type="Opaque",
            metadata=meta,
            data=data,
        )

        # create or update secret
        try:
            self.kube.read_namespaced_secret(name, self.namespace)
            r = self.kube.patch_namespaced_secret(name, self.namespace, secret)
            return r.metadata.name
        except client.exceptions.ApiException as e:
            if e.status == 404:
                r = self.kube.create_namespaced_secret(self.namespace, secret)
                return r.metadata.name
            else:
                raise
