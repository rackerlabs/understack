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
    cfg.StrOpt(
        "shared_nautobot_namespace_name",
        default="Global",
        help=(
            "Nautobot namespace name that will house all external prefixes, i.e "
            "prefixes that need to be routable outside of a tenant environment."
        ),
    ),
]

l3_svc_cisco_asa_opts = [
    cfg.StrOpt(
        "user_agent",
        help="User-Agent for requests to Cisco ASA",
        default="ASDM",
    ),
    cfg.StrOpt(
        "username",
        help="username for requests to the Cisco ASA",
    ),
    cfg.StrOpt(
        "password",
        help="password for requests to the Cisco ASA",
    ),
    cfg.StrOpt(
        "outside_interface",
        help="ASA interface for outside connections",
        default="OUTSIDE",
    ),
]


def register_ml2_type_understack_opts(config):
    config.register_opts(type_understack_opts, "ml2_type_understack")


def register_ml2_understack_opts(config):
    config.register_opts(mech_understack_opts, "ml2_understack")


def register_l3_svc_cisco_asa_opts(config):
    config.register_opts(l3_svc_cisco_asa_opts, "l3_service_cisco_asa")
