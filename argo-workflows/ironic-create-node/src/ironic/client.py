from ironicclient import client as iclient
from keystoneauth1 import session
from keystoneauth1.identity import v3


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
        sess = session.Session(
            auth=auth, verify=(not insecure_ssl), app_name="nautobot"
        )
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

        return self.client.node.create(
            os_ironic_api_version="1.82", **node_data
        )

    def list_nodes(self):
        self._ensure_logged_in()

        return self.client.node.list()

    def _ensure_logged_in(self):
        if not self.logged_in:
            self.login()
