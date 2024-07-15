import json
import logging
import sys

from ironic.client import IronicClient
from ironic.secrets import read_secret

logger = logging.getLogger(__name__)


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
