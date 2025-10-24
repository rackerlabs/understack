from oslo_config import cfg

CONF = cfg.CONF


def setup_conf():
    grp = cfg.OptGroup("nova_understack")
    opts = [
        cfg.StrOpt(
            "nautobot_base_url",
            help="Nautobot's base URL",
            default="https://nautobot.nautobot.svc",
        ),
        cfg.StrOpt("nautobot_api_key", help="Nautotbot's API key", default=""),
        cfg.StrOpt(
            "argo_api_url",
            help="Argo Workflows API url",
            default="https://argo-server.argo.svc:2746",
        ),
        cfg.StrOpt(
            "ansible_playbook_filename",
            help="Name of the Ansible playbook to execute when server is created.",
            default="storage_on_server_create.yml",
        ),
        cfg.BoolOpt(
            "ip_injection_enabled",
            help="Controls if Nova should inject storage IPs to config drive.",
            default=True,
        ),
        cfg.StrOpt(
            "storage_target_a_prefix",
            help="Storage Networking Target Prefix A-side",
            default="100.127.0.0/17",
        ),
        cfg.StrOpt(
            "storage_target_b_prefix",
            help="Storage Networking Target Prefix B-side",
            default="100.127.128.0/17",
        ),
        cfg.StrOpt(
            "storage_client_a_prefix",
            help="Storage Networking Client Prefix A-side",
            default="100.126.0.0/17",
        ),
        cfg.StrOpt(
            "storage_client_b_prefix",
            help="Storage Networking Client Prefix B-side",
            default="100.126.128.0/17",
        ),
    ]
    cfg.CONF.register_group(grp)
    cfg.CONF.register_opts(opts, group=grp)


setup_conf()
