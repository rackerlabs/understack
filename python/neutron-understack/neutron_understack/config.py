from oslo_config import cfg

type_understack_opts = [
    cfg.StrOpt(
        "provisioning_network",
        help="provisioning_network ID as configured in ironic.conf",
        default="change_me",
    ),
]

mech_understack_opts = [
    cfg.StrOpt(
        "nb_url",
        help="Nautobot URL",
    ),
    cfg.StrOpt(
        "nb_token",
        help="Nautobot API token",
    ),
    cfg.StrOpt(
        "ucvni_group",
        help="hack",
    ),
    cfg.StrOpt(
        "undersync_url",
        help="Undersync URL",
    ),
    cfg.StrOpt(
        "undersync_token",
        help=(
            "Undersync API token. If not provided, "
            "the '/etc/undersync/token' will be read instead."
        ),
    ),
    cfg.BoolOpt(
        "undersync_dry_run", default=True, help="Call Undersync with dry-run mode"
    ),
]


def register_ml2_type_understack_opts(config):
    config.register_opts(type_understack_opts, "ml2_type_understack")


def register_ml2_understack_opts(config):
    config.register_opts(mech_understack_opts, "ml2_understack")
