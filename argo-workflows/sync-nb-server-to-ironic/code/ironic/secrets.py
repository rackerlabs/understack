import os
import re
import logging

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

