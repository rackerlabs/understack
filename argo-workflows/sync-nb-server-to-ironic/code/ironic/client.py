from ironicclient import client as iclient
from keystoneauth1 import session
from keystoneauth1.identity import v3
from typing import List


class IronicClient:
    def __init__(
        self,
        svc_url: str,
        username: str,
        password: str,
        auth_url: str,
        tenant_name: str,
    ) -> None:
        self.svc_url = svc_url
        self.username = username
        self.password = password
        self.auth_url = auth_url
        self.tenant_name = tenant_name
        self.logged_in = False
        self.os_ironic_api_version = "1.82"

    def login(self):
        auth = v3.Password(
            auth_url=self.auth_url,
            username=self.username,
            password=self.password,
            project_name=self.tenant_name,
            project_domain_name="Default",
            user_domain_name="Default",
        )
        insecure_ssl = True
        sess = session.Session(auth=auth, verify=(not insecure_ssl), app_name="nautobot")
        self.client = iclient.Client(
            1,
            endpoint_override=self.svc_url,
            session=sess,
            insecure=insecure_ssl,
        )
        self.client.negotiate_api_version()
        self.logged_in = True

    def create_node(self, node_data: dict):
        self._ensure_logged_in()

        return self.client.node.create(os_ironic_api_version=self.os_ironic_api_version, **node_data)

    def list_nodes(self):
        self._ensure_logged_in()

        return self.client.node.list()

    def get_node(self, node_ident: str, fields: list[str] | None = None):
        self._ensure_logged_in()

        return self.client.node.get(node_ident, fields, os_ironic_api_version=self.os_ironic_api_version)

    def update_node(self, node_id, patch):
        self._ensure_logged_in()

        return self.client.node.update(node_id, patch, os_ironic_api_version=self.os_ironic_api_version)

    def create_port(self, port_data: dict):
        self._ensure_logged_in()

        return self.client.port.create(os_ironic_api_version=self.os_ironic_api_version, **port_data)

    def update_port(self, port_id: str, patch: List):
        self._ensure_logged_in()

        return self.client.port.update(port_id, patch, os_ironic_api_version=self.os_ironic_api_version)

    def delete_port(self, port_id: str):
        self._ensure_logged_in()

        return self.client.port.delete(port_id, os_ironic_api_version=self.os_ironic_api_version)

    def list_ports(self, node_id: dict):
        self._ensure_logged_in()

        return self.client.port.list(node=node_id, detail=True)

    def _ensure_logged_in(self):
        if not self.logged_in:
            self.login()
