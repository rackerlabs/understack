from keystoneauth1 import loading as ks_loading
from keystoneauth1 import session as ks_session
from oslo_config import cfg

_OPT_GRP_ML2_UNDERSTACK = "ml2_understack"
_OPT_GRP_IRONIC = "ironic"
_OPT_GRP_L3_SVC_CISCO_ASA = "l3_service_cisco_asa"
_OPT_GRP_UNDERSTACK_VNI = "understack_vni"
_OPT_GRP_NETDEV_RECONCILE = "netdev_router_reconcile"

_mech_understack_opts = [
    cfg.StrOpt(
        "undersync_url",
        help="Undersync URL",
    ),
    cfg.BoolOpt(
        "undersync_dry_run", default=True, help="Call Undersync with dry-run mode"
    ),
    cfg.StrOpt(
        "network_node_switchport_physnet",
        help=(
            "Name of the physnet configured on a network node's"
            "baremetal port that provides connectivity to OVN."
        ),
    ),
    cfg.ListOpt(
        "default_tenant_vlan_id_range",
        default=[1, 3799],
        item_type=cfg.types.Integer(min=1, max=4094),
        help=(
            "List of 2 comma separated integers, that represents a VLAN range, that"
            "will be used for mapped VLANs on the switches."
        ),
    ),
]


_l3_svc_cisco_asa_opts = [
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

_understack_vni_opts = [
    cfg.ListOpt(
        "vni_ranges",
        default=["1:16777215"],
        item_type=cfg.types.String(),
        help=(
            "Comma-separated list of VNI ranges available for automatic "
            "Understack VRF router VNI allocation. Each entry is either a "
            "single VNI or an inclusive start:end range."
        ),
    ),
]


_netdev_reconcile_opts = [
    cfg.BoolOpt(
        "enabled",
        default=True,
        help=(
            "Run the periodic netdev-router reconciler in the OVN maintenance "
            "worker. It releases panos Ironic nodes whose instance_uuid names "
            "a router that no longer exists. Set to false to stop it from "
            "changing any node state; set dry_run to inspect what it would do "
            "without changing anything."
        ),
    ),
    cfg.BoolOpt(
        "dry_run",
        default=False,
        help=(
            "Log the netdev nodes the reconciler would release without "
            "releasing them. Use this to confirm the candidate set in a new "
            "region before letting it act."
        ),
    ),
]


def list_understack_opts():
    return [
        (_OPT_GRP_ML2_UNDERSTACK, _mech_understack_opts),
    ]


def list_ironic_opts():
    return [
        (
            _OPT_GRP_IRONIC,
            [
                *ks_loading.get_adapter_conf_options(include_deprecated=False),
                *ks_loading.get_session_conf_options(),
                *ks_loading.get_auth_plugin_conf_options("v3password"),
            ],
        )
    ]


def list_cisco_asa_opts():
    return [
        (_OPT_GRP_L3_SVC_CISCO_ASA, _l3_svc_cisco_asa_opts),
    ]


def list_understack_vni_opts():
    return [
        (_OPT_GRP_UNDERSTACK_VNI, _understack_vni_opts),
    ]


def list_netdev_reconcile_opts():
    return [
        (_OPT_GRP_NETDEV_RECONCILE, _netdev_reconcile_opts),
    ]


def register_ml2_understack_opts(config):
    config.register_opts(_mech_understack_opts, _OPT_GRP_ML2_UNDERSTACK)


def register_ironic_opts(config):
    ks_loading.register_adapter_conf_options(config, _OPT_GRP_IRONIC)
    ks_loading.register_session_conf_options(config, _OPT_GRP_IRONIC)
    ks_loading.register_auth_conf_options(config, _OPT_GRP_IRONIC)


def register_l3_svc_cisco_asa_opts(config):
    config.register_opts(_l3_svc_cisco_asa_opts, _OPT_GRP_L3_SVC_CISCO_ASA)


def register_understack_vni_opts(config):
    config.register_opts(_understack_vni_opts, _OPT_GRP_UNDERSTACK_VNI)


def register_netdev_reconcile_opts(config):
    config.register_opts(_netdev_reconcile_opts, _OPT_GRP_NETDEV_RECONCILE)


def get_session(group: str) -> ks_session.Session:
    auth = ks_loading.load_auth_from_conf_options(cfg.CONF, group)
    session = ks_loading.load_session_from_conf_options(cfg.CONF, group, auth=auth)
    return session
