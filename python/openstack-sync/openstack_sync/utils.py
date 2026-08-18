"""Shared utilities for all openstack-sync hooks.

Provides Kubernetes secret access and OpenStack connection management so
every hook can use the same building blocks without duplication.
"""

from __future__ import annotations

import base64
import os
from typing import Any

import openstack
import yaml
from kubernetes import client
from kubernetes import config as k8s_config
from openstack.config import loader as os_config_loader


def read_secret_key(secret_name: str, secret_key: str, namespace: str) -> str:
    """Read a single key from a Kubernetes Secret and return its decoded value.

    Configures the client automatically:
    - Inside a cluster: uses the pod's service-account token.
    - Outside a cluster: falls back to the local kubeconfig (development).

    Args:
        secret_name: Name of the Kubernetes Secret to read.
        secret_key: Key within the Secret's data map.
        namespace: Namespace the Secret lives in.

    Returns:
        The base64-decoded string value of the key.

    Raises:
        KeyError: When ``secret_key`` is not present in the Secret's data.
    """
    try:
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException:
        k8s_config.load_kube_config()

    v1 = client.CoreV1Api()
    secret = v1.read_namespaced_secret(name=secret_name, namespace=namespace)
    raw = (secret.data or {}).get(secret_key)
    if raw is None:
        raise KeyError(
            f"Key {secret_key!r} not found in secret {secret_name!r} "
            f"(namespace {namespace!r})."
        )
    return base64.b64decode(raw).decode("utf-8")


def pod_namespace() -> str:
    """Return the current pod's namespace.

    Reads ``POD_NAMESPACE`` from the environment, defaulting to ``"default"``
    when absent (e.g. local development runs).
    """
    return os.environ.get("POD_NAMESPACE", "openstack")


# Memoised OpenStack connections, keyed by (secret_name, cloud_name).
_connection_cache: dict[tuple[str, str], Any] = {}


def get_openstack_connection(secret_name: str, cloud_name: str) -> Any:
    """Return a memoised ``openstack.connection.Connection``.

    Credentials are loaded from the named Kubernetes Secret via
    ``read_secret_key``.  The secret must contain a key ``clouds.yaml``
    holding a standard OpenStack clouds.yaml file.  Connections are cached
    per ``(secret_name, cloud_name)`` pair so multiple reconcile calls within
    the same process re-use the same authenticated session.

    Args:
        secret_name: Name of the Kubernetes Secret containing ``clouds.yaml``.
        cloud_name: Name of the cloud entry within the ``clouds.yaml`` to use.

    Returns:
        An authenticated ``openstack.connection.Connection``.
    """
    cache_key = (secret_name, cloud_name)
    if cache_key in _connection_cache:
        return _connection_cache[cache_key]

    clouds_yaml_text = read_secret_key(secret_name, "clouds.yaml", pod_namespace())

    # openstack.connect(cloud=name) resolves the named cloud from files on
    # disk, which fails inside a container with no clouds.yaml present.
    # Instead, parse the YAML from the Secret and inject it directly into
    # the SDK config loader — no filesystem writes required.
    loader = os_config_loader.OpenStackConfig(
        config_files=[],
        vendor_files=[],
        load_yaml_config=False,
        load_envvars=False,
    )
    loader.cloud_config = yaml.safe_load(clouds_yaml_text)
    region = loader.get_one(cloud=cloud_name)
    conn = openstack.connection.Connection(config=region)
    _connection_cache[cache_key] = conn
    return conn
