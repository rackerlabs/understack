"""Refresh Ironic's Dex certificate for subsequent OIDC configuration steps."""

import configparser
import json
import socket
import ssl
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

CONF = Path("/etc/ironic/ironic.conf.d/bmc-sso-oidc.conf")
NAMESPACE_FILE = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")
CONFIGMAP = "ironic-oidc-https-cert"


def main():
    config = configparser.ConfigParser(interpolation=None)
    config.read(CONF)  # silently no-ops when CONF is absent (secret is optional)
    discovery_url = config.get("drac", "oidc_discovery_url", fallback="").strip()
    if not discovery_url:
        print(f"No oidc_discovery_url in {CONF}, skipping", flush=True)
        return

    endpoint = urlsplit(discovery_url)
    if endpoint.scheme != "https" or not endpoint.hostname:
        raise ValueError("oidc_discovery_url must be an HTTPS URL with a hostname")

    print(f"Fetching TLS certificate from {endpoint.netloc}", flush=True)
    context = ssl.create_default_context()
    with socket.create_connection(
        (endpoint.hostname, endpoint.port or 443), timeout=15
    ) as connection:
        with context.wrap_socket(connection, server_hostname=endpoint.hostname) as tls:
            pem = ssl.DER_cert_to_PEM_cert(tls.getpeercert(binary_form=True))
            print(f"notAfter={tls.getpeercert()['notAfter']}", flush=True)

    namespace = NAMESPACE_FILE.read_text().strip()
    configmap = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": CONFIGMAP, "namespace": namespace},
        "data": {"dex-server.pem": pem},
    }
    subprocess.run(
        ["kubectl", "apply", "-n", namespace, "-f", "-"],
        input=json.dumps(configmap),
        text=True,
        check=True,
    )
    print(f"ConfigMap {CONFIGMAP} updated", flush=True)


if __name__ == "__main__":
    main()
