import logging

from keystoneauth1 import loading as ks_loading
from openstack import connection
from openstack.baremetal.baremetal_service import BaremetalService
from openstack.baremetal.v1.port import Port as BaremetalPort
from oslo_config import cfg

# IRONIC_SESSION = None
def _green_socket_modules():
    from eventlet.green import socket
    return [('socket', socket)]

import eventlet.patcher
eventlet.patcher.__dict__['_green_socket_modules'] = _green_socket_modules

LOG = logging.getLogger(__name__)


class IronicClient:
    def __init__(self):
        # LOG.debug("creating ironic client")
        self._session = None
        # LOG.debug("created ironic client")

    def _get_session(self, group: str) -> ks_loading.session.Session:
        auth = ks_loading.load_auth_from_conf_options(cfg.CONF, group)
        session = ks_loading.load_session_from_conf_options(cfg.CONF, group, auth=auth)
        return session

    # def _get_ironic_client(self) -> BaremetalService:
    #     global IRONIC_SESSION
    #     if not IRONIC_SESSION:
    #         IRONIC_SESSION = self._get_session("ironic")
    #
    #     LOG.debug("got session, making ironic connection")

    @property
    def irclient(self):
        if not self._session:
            LOG.debug("creating ironic session")
            self._session = self._get_session("ironic")
            LOG.debug("created ironic session")

        return connection.Connection(
            session=self._session,
            oslo_conf=cfg.CONF,
            connect_retries=cfg.CONF.http_retries,
        ).baremetal

    def baremetal_port_physical_network(self, local_link_info: dict) -> str | None:
        port = self._port_by_local_link(local_link_info)
        return port.physical_network if port else None

    def _port_by_local_link(self, local_link_info: dict) -> BaremetalPort | None:
        try:
            return next(
                self.irclient.ports(details=True, local_link_connection=local_link_info)
            )
        except StopIteration:
            return None
