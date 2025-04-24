from keystoneauth1 import loading as ks_loading
from openstack import connection
from openstack.baremetal.baremetal_service import BaremetalService
from openstack.baremetal.v1.port import Port as BaremetalPort
from oslo_config import cfg


class IronicClient:
    def __init__(self):
        self.irclient = self._get_ironic_client()

    def _get_session(self, group: str) -> ks_loading.session.Session:
        auth = ks_loading.load_auth_from_conf_options(cfg.CONF, group)
        session = ks_loading.load_session_from_conf_options(
            cfg.CONF, group, auth=auth)
        return session

    def _get_ironic_client(self) -> BaremetalService:
        session = self._get_session("ironic")

        return connection.Connection(
            session=session, oslo_conf=cfg.CONF,
            connect_retries=cfg.CONF.http_retries).baremetal

    def baremetal_port_by_mac(self, mac_addr: str) -> BaremetalPort | None:
        try:
            return next(self.irclient.ports(details=True, address=mac_addr))
        except StopIteration:
            return None

    def baremetal_port_physical_network(self, mac_addr: str) -> str | None:
        port = self.baremetal_port_by_mac(mac_addr)
        return port.physical_network if port else None
