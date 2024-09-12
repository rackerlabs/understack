from kubernetes import client, config
import os
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class ArgoWorkflow:
    def __init__(self, namespace="argo-events", config_file=None):

        if config_file:
            config.load_kube_config(config_file)
        else:
            config.load_incluster_config()

        self.kube = client.CoreV1Api()
        self.kube_custom = client.CustomObjectsApi()
        self.namespace = namespace

    def get_pod(self, name):
        r = self.kube.read_namespaced_pod(name, self.namespace)
        return r.metadata

    def create_secret(self, name: str, data: Dict, persist=False) -> str:
        """
        create_secret creates a kubernetes secret, setting ownerReferences to provide garbage collection.

        :param name: metadata.name of the kubernetes secret
        :param data: data dict to be stored in the secret
        :param persist: whether this secret should persist or be removed with the owning Workflow
        :return: the name of the kubernetes secret
        """

        secret = client.V1Secret()
        secret.api_version = "v1"
        secret.data = data
        secret.kind = "Secret"
        secret.type = "Opaque"
        secret.metadata = {"name": f"{name}"}

        # to allow for kubernetes' garbage collection to reap this secret, we attempt to detect the owning resource,
        # and then add it to the ownerReferences list.
        if not persist:
            try:
                # if KUBERNETES_POD_UID is not explicitly defined in the container env, pod get permissions will need
                # be set for the service account running this workflow
                owner_name = os.environ["DEVICE_ID"]
                owner_id = os.getenv("KUBERNETES_POD_UID")
                if not owner_id:
                    owner_metadata = self.get_pod(owner_name)
                    owner_id = owner_metadata.uid

                secret.metadata.update(
                    {
                        "name": f"{name}-{owner_id}",
                        "ownerReferences": [
                            {
                                "apiVersion": "v1",
                                "blockOwnerDeletion": True,
                                "controller": True,
                                "kind": "Pod",
                                "name": owner_name,
                                "uid": owner_id,
                            }
                        ],
                    }
                )
            except KeyError:
                raise Exception("Unable to determine ownership of secret.")

        # create or update secret
        try:
            self.kube.read_namespaced_secret(secret.metadata["name"], self.namespace)
            r = self.kube.patch_namespaced_secret(secret.metadata["name"], self.namespace, secret)
            return r.metadata.name
        except client.exceptions.ApiException as e:
            if e.status == 404:
                r = self.kube.create_namespaced_secret(self.namespace, secret)
                return r.metadata.name
            else:
                raise Exception(e)
