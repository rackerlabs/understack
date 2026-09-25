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
    ]
    cfg.CONF.register_group(grp)
    cfg.CONF.register_opts(opts, group=grp)

    # Register network device credential groups (loaded from network_devices.conf)
    # These sections are populated from /etc/ironic/ironic.conf.d/network_devices.conf
    # which is mounted via etcSources from the network-device-credentials-ini secret
    for group_name in ["panos", "f5", "service_accounts"]:
        grp = cfg.OptGroup(group_name)
        cfg.CONF.register_group(grp)
        # Options are defined in the INI file, not pre-registered here


setup_conf()
