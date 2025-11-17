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
        cfg.StrOpt(
            "nautobot_url",
            help="Nautobot API URL",
            default=None,
        ),
        cfg.StrOpt(
            "nautobot_token",
            help="Nautobot API token",
            secret=True,
            default=None,
        ),
    ]
    cfg.CONF.register_group(grp)
    cfg.CONF.register_opts(opts, group=grp)


setup_conf()
