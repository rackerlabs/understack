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
        session = ks_loading.load_session_from_conf_options(cfg.CONF, group, auth=auth)
        return session

    def _get_ironic_client(self) -> BaremetalService:
        session = self._get_session("ironic")

        return connection.Connection(
            session=session, oslo_conf=cfg.CONF, connect_retries=cfg.CONF.http_retries
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

    def baremetal_node_name(self, node_uuid: str) -> str | None:
        try:
            node = self.irclient.get_node(node_uuid)
            return node.name if node else None
        except Exception:
            return None

    def baremetal_node_uuid(self, node_name: str) -> str | None:
        try:
            node = self.irclient.get_node(node_name)
            return node.id if node else None
        except Exception:
            return None
