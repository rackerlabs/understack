import contextlib

from keystoneauth1 import loading as ks_loading
from keystoneauth1 import session as ks_session
from oslo_config import cfg

_OPT_GRP_ML2_UNDERSTACK = "ml2_understack"
_OPT_GRP_IRONIC = "ironic"
_OPT_GRP_L3_SVC_CISCO_ASA = "l3_service_cisco_asa"
_OPT_GRP_UNDERSTACK_VNI = "understack_vni"

_mech_understack_opts = [
    cfg.StrOpt(
        "nb_url",
        help="Nautobot URL",
        required=False,
    ),
    cfg.StrOpt(
        "nb_token",
        help="Nautobot API token",
        required=False,
    ),
    cfg.StrOpt(
        "ucvni_group",
        help="hack",
    ),
    cfg.StrOpt(
        "undersync_url",
        help="Undersync URL",
    ),
    cfg.BoolOpt(
        "undersync_dry_run", default=True, help="Call Undersync with dry-run mode"
    ),
    cfg.StrOpt(
        "provisioning_network",
        help="provisioning_network ID as configured in ironic.conf",
        default="change_me",
    ),
    cfg.StrOpt(
        "shared_nautobot_namespace_name",
        default="Global",
        help=(
            "Nautobot namespace name that will house all external prefixes, i.e "
            "prefixes that need to be routable outside of a tenant environment."
        ),
    ),
    # TODO:: this can very likely be deprecated now
    cfg.StrOpt(
        "network_node_switchport_uuid",
        help=(
            "Nautobot UUID of the network node's switchport interface, that "
            "is used to trunk all vlans used by a neutron router."
        ),
    ),
    cfg.StrOpt(
        "network_node_switchport_physnet",
        help=(
            "Name of the physnet configured on a network node's"
            "baremetal port that provides connectivity to OVN."
        ),
    ),
    cfg.BoolOpt(
        "enforce_unique_vlans_in_fabric",
        default=True,
        help=(
            "When enabled, Neutron performs an extra check during the creation of a"
            "new VLAN network. This check ensures that the VLAN ID being assigned is"
            "not already in use within a fabric. The verification is handled by "
            "Nautobot."
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


def register_ml2_understack_opts(config):
    config.register_opts(_mech_understack_opts, _OPT_GRP_ML2_UNDERSTACK)


def register_ironic_opts(config):
    ks_loading.register_adapter_conf_options(config, _OPT_GRP_IRONIC)
    ks_loading.register_session_conf_options(config, _OPT_GRP_IRONIC)
    ks_loading.register_auth_conf_options(config, _OPT_GRP_IRONIC)


def register_l3_svc_cisco_asa_opts(config):
    config.register_opts(_l3_svc_cisco_asa_opts, _OPT_GRP_L3_SVC_CISCO_ASA)


def register_understack_vni_opts(config):
    with contextlib.suppress(cfg.DuplicateOptError):
        config.register_opts(_understack_vni_opts, _OPT_GRP_UNDERSTACK_VNI)


def get_session(group: str) -> ks_session.Session:
    auth = ks_loading.load_auth_from_conf_options(cfg.CONF, group)
    session = ks_loading.load_session_from_conf_options(cfg.CONF, group, auth=auth)
    return session
