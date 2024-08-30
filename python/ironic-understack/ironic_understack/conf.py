from oslo_config import cfg
CONF = cfg.CONF


def setup_conf():
    grp = cfg.OptGroup("ironic_understack")
    opts = [
        cfg.StrOpt(
            "flavors_dir",
            help="directory storing Flavor description YAML files",
            default="/var/lib/understack/flavors/undercloud-nautobot-device-types.git/flavors",
        )
    ]
    cfg.CONF.register_group(grp)
    cfg.CONF.register_opts(opts, group=grp)


setup_conf()
