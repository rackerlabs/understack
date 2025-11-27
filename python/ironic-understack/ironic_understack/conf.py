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


setup_conf()
