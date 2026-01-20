"""helper to setup OpenStack clients."""

# attempt to prevent re-export
import os as _os
import sys as _sys
from importlib import metadata as _meta

from ironicclient.client import Client as IronicClient
from ironicclient.client import get_client as _get_ironic_client
from openstack import config as _os_config
from openstack.connection import Connection

try:
    _pkg_ver = _meta.version(str(__package__).split(".")[0])
except Exception:
    _pkg_ver = "dev"

try:
    _prog_name = _os.path.basename(_sys.argv[0]) or "local"
except Exception:
    _prog_name = "local"


def _get_os_cloud_region(cloud=None, region_name=""):
    """Returns a keystoneauth1 Session based on our clouds.yaml."""
    return _os_config.get_cloud_region(
        load_yaml_config=True,
        load_envvars=True,
        app_name=_prog_name,
        app_version=_pkg_ver,
        cloud=cloud,
        region_name=region_name,
    )


def get_openstack_client(cloud=None, region_name="") -> Connection:
    """Returns an OpenStackSDK Connection based on our clouds.yaml."""
    cloud_region = _get_os_cloud_region(cloud, region_name)

    return Connection(config=cloud_region)


def get_ironic_client(cloud=None, region_name="") -> IronicClient:  # type: ignore
    """Returns our Ironic Client wrapper configured from our clouds.yaml."""
    cloud_region = _get_os_cloud_region(cloud, region_name)
    client = _get_ironic_client(
        api_version="1",
        session=cloud_region.get_session(),
        os_ironic_api_version="latest",
        region_name=cloud_region.region_name,
    )
    client.negotiate_api_version()
    return client


__all__ = [
    "get_openstack_client",
    "get_ironic_client",
]
