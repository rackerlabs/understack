from oslo_config import cfg

CONF = cfg.CONF


def setup_conf():
    grp = cfg.OptGroup("ironic_understack")
    opts = [
        cfg.StrOpt(
            "device_types_dir",
            help="directory storing Device Type description YAML files",
            default="/var/lib/understack/device-types",
        ),
        cfg.DictOpt(
            "switch_name_vlan_group_mapping",
            help="Dictionary of switch hostname suffix to vlan group name",
            default={
                "1": "network",
                "2": "network",
                "3": "network",
                "4": "network",
                "1f": "storage",
                "2f": "storage",
                "3f": "storage-appliance",
                "4f": "storage-appliance",
                "1d": "bmc",
            },
        ),
        cfg.StrOpt(
            "kea_url",
            default="http://kea-kea-dhcp-headless.openstack.svc.cluster.local:8000",
            help="URL of the Kea DHCP server's HTTP API endpoint. "
            "This endpoint is used for managing DHCP "
            "configuration, reservations, leases and subnet "
            "operations through Kea's HTTP API interface.",
        ),
        cfg.StrOpt(
            "kea_log_requests",
            default="false",
            help="Enable logging of Kea API requests and responses.",
        ),
        cfg.StrOpt(
            "kea_log_requests_body",
            default="false",
            help="Enable logging of the body of Kea API requests and responses.",
        ),
        cfg.IntOpt(
            "kea_request_timeout",
            default=10,
            help="Timeout in seconds for requests to the Kea API.",
        ),
        cfg.IntOpt(
            "kea_max_retries",
            default=3,
            help="Maximum number of retry attempts for failed requests.",
        ),
        cfg.StrOpt(
            "kea_proxy_listen_host",
            default="0.0.0.0",  # noqa: S104 -- binds within the pod network namespace
            help="Host/address the kea_proxy service binds to.",
        ),
        cfg.IntOpt(
            "kea_proxy_listen_port",
            default=9080,
            help="Port the kea_proxy service binds to.",
        ),
        cfg.StrOpt(
            "kea_proxy_url",
            default="http://ironic-kea-proxy.openstack.svc.cluster.local:9080",
            help="URL of the kea_proxy service used by the DHCP driver to "
            "manage reservations and leases on its behalf.",
        ),
    ]
    cfg.CONF.register_group(grp)
    cfg.CONF.register_opts(opts, group=grp)


setup_conf()
