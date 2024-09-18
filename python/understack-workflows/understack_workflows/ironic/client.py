from understack_workflows.openstack.client import get_ironic_client


class IronicClient:
    def __init__(
        self,
    ) -> None:
        """Initialize our ironicclient wrapper."""
        self.logged_in = False

    def login(self):
        self.client = get_ironic_client()
        self.logged_in = True

    def create_node(self, node_data: dict):
        self._ensure_logged_in()

        return self.client.node.create(**node_data)

    def list_nodes(self):
        self._ensure_logged_in()

        return self.client.node.list()

    def get_node(self, node_ident: str, fields: list[str] | None = None):
        self._ensure_logged_in()

        return self.client.node.get(
            node_ident,
            fields,
        )

    def update_node(self, node_id, patch):
        self._ensure_logged_in()

        return self.client.node.update(
            node_id,
            patch,
        )

    def create_port(self, port_data: dict):
        self._ensure_logged_in()

        return self.client.port.create(**port_data)

    def update_port(self, port_id: str, patch: list):
        self._ensure_logged_in()

        return self.client.port.update(
            port_id,
            patch,
        )

    def delete_port(self, port_id: str):
        self._ensure_logged_in()

        return self.client.port.delete(
            port_id,
        )

    def list_ports(self, node_id: dict):
        self._ensure_logged_in()

        return self.client.port.list(node=node_id, detail=True)

    def _ensure_logged_in(self):
        if not self.logged_in:
            self.login()
