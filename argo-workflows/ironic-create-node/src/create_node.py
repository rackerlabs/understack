import json
import logging
import os
import re
import sys

from ironic.client import IronicClient

logger = logging.getLogger(__name__)

def read_secret(secret_name: str) -> str:
    """Retrieve value of Kubernetes secret"""
    def normalized(name):
        return re.sub(r'[^A-Za-z0-9-_]', '', name)

    base_path = os.environ.get('SECRETS_BASE_PATH', '/etc/ironic-secrets/')
    secret_path = os.path.join(base_path, normalized(secret_name))
    try:
        return open(secret_path, "r").read()
    except FileNotFoundError:
        logger.error(f"Secret {secret_name} is not defined.")
        return ""

if len(sys.argv) < 1:
    raise ValueError("Please provide node configuration in JSON format as first argument.")

logger.info("Pushing device new node to Ironic.")
client = IronicClient(
    svc_url=read_secret("IRONIC_SVC_URL"),
    username=read_secret("IRONIC_USERNAME"),
    password=read_secret("IRONIC_PASSWORD"),
    auth_url=read_secret("IRONIC_AUTH_URL"),
    tenant_name=read_secret("IRONIC_TENANT"),
)

node_config = json.loads(sys.argv[1])
response = client.create_node(node_config)
logger.debug(response)
