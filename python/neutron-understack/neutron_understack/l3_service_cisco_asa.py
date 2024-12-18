# inspired from
# https://docs.openstack.org/neutron/latest/admin/config-router-flavor-ovn.html

import ssl

import requests
import urllib3
from neutron.services.l3_router.service_providers import base
from neutron_lib.callbacks import registry
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class CustomHttpAdapter(requests.adapters.HTTPAdapter):
    """Custom adapter for bad ASA SSL."""

    def __init__(self, ssl_context=None, **kwargs):
        """Init to match requests HTTPAdapter."""
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = urllib3.poolmanager.PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=self.ssl_context,
        )


def get_legacy_session():
    """Support bad ASA SSL."""
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = False
    ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
    session = requests.session()
    session.mount("https://", CustomHttpAdapter(ctx))
    return session


@registry.has_registry_receivers
class CiscoAsa(base.L3ServiceProvider):
    use_integrated_agent_scheduler = True
