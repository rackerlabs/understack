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
    ]
    cfg.CONF.register_group(grp)
    cfg.CONF.register_opts(opts, group=grp)


setup_conf()
