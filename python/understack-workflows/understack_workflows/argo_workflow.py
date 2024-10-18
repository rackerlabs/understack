import logging

from kubernetes import client
from kubernetes import config

logger = logging.getLogger(__name__)

API_VERSION = "argoproj.io/v1alpha1"


def create_secret(
    namespace: str, workflow_name: str, owner_uid: str, name: str, data: dict
) -> str:
    """Creates a kubernetes secret.

    :param namespace: namespace to put secret in
    :param workflow_name: for owner
    :param owner_uid: pod uid
    :param name: metadata.name of the kubernetes secret
    :param data: data dict to be stored in the secret
    :return: the name of the kubernetes secret

    Used to share sensitive data to subsequent steps in a workflow

    Sets metadata.ownerReferences to the workflow to enable garbage collection.
    The secret is cleaned up once the workflow is finished

    note: the Pod's uid can be passed into the container with something like:

        env:
            - name: WF_UID
            value: "{{workflow.uid}}"
    """
    config.load_incluster_config()

    owner = client.V1OwnerReference(
        api_version=API_VERSION,
        kind="Workflow",
        name=workflow_name,
        uid=owner_uid,
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

    kube = client.CoreV1Api()
    # create or update secret
    try:
        kube.read_namespaced_secret(name, namespace)
        r = kube.patch_namespaced_secret(name, namespace, secret)
        return r.metadata.name
    except client.exceptions.ApiException as e:
        if e.status == 404:
            r = kube.create_namespaced_secret(namespace, secret)
            return r.metadata.name
        else:
            raise
