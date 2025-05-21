from oslo_config import cfg
from ovsdbapp.backend.ovs_idl import connection
from ovsdbapp.schema.ovn_northbound import impl_idl


def ovn_nb_api_transaction(func):
    def wrapper(self, *args, **kwargs):
        with self.ovn_nb_api.transaction(check_error=True) as txn:
            result = func(self, *args, **kwargs)
            if result is not None:
                txn.add(result)
            return txn

    return wrapper


class OVNClient:
    def __init__(self):
        idl = connection.OvsdbIdl.from_server(
            cfg.CONF.ovn.ovn_nb_connection, "OVN_Northbound"
        )
        self.conn = connection.Connection(idl=idl, timeout=10)
        self.ovn_nb_api = impl_idl.OvnNbApiIdlImpl(self.conn)

    @ovn_nb_api_transaction
    def add_localnet_port(
        self,
        switch_name="",
        network_name="",
        port_name="",
        tag=0,
        may_exist=True,
    ):
        return self.ovn_nb_api.lsp_add(
            switch_name,
            port_name,
            may_exist=may_exist,
            type="localnet",
            parent_name=[],
            tag=tag,
            options={
                "network_name": network_name,
            },
            addresses=["unknown"],
        )

    @ovn_nb_api_transaction
    def remove_localnet_port(self, switch_name, port_name):
        return self.ovn_nb_api.lsp_del(port_name, switch_name)


if __name__ == "__main__":
    ovn_opts = [cfg.StrOpt("ovn_nb_connection", default="tcp:10.106.146.16:6641")]
    cfg.CONF.register_opts(ovn_opts, group="ovn")
    # cfg.CONF.set_override('ovn_nb_connection', '', group='ovn')
    cl = OVNClient()
    SWITCH = "3e97e6d7-58d1-436e-9369-dad3ad1fad6e"
    PORT_NAME = "marekport"
    print("Adding port:")
    print(cl.add_localnet_port(SWITCH, "f20-1-network", PORT_NAME, 667))
    print(cl.add_localnet_port(SWITCH, "f20-1-network", PORT_NAME, 667))
    print("Removing:")
    print(cl.remove_localnet_port(SWITCH, PORT_NAME))
