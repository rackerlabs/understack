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

    # PAN-OS credentials
    panos_opts = [
        cfg.StrOpt("username", default="admin", help="PAN-OS username"),
        cfg.StrOpt("standard_password", secret=True, help="PAN-OS standard password"),
        cfg.StrOpt("preconfig_password", secret=True, help="PAN-OS preconfig password"),
        cfg.StrOpt(
            "factory_password",
            default="admin",
            secret=True,
            help="PAN-OS factory password",
        ),
        cfg.StrOpt("panorama_master_key", secret=True, help="Panorama master key"),
        cfg.BoolOpt(
            "verify_ssl",
            default=False,
            help="Verify the TLS certificate of the PAN-OS XML API. Off by "
            "default because appliances ship with self-signed certificates.",
        ),
    ]
    panos_grp = cfg.OptGroup("netdev_panos", title="PAN-OS Credentials")
    cfg.CONF.register_group(panos_grp)
    cfg.CONF.register_opts(panos_opts, group=panos_grp)

    # F5 credentials
    f5_opts = [
        cfg.StrOpt("root_username", default="root", help="F5 root username (AOM)"),
        cfg.StrOpt(
            "root_standard_password", secret=True, help="F5 root standard password"
        ),
        cfg.StrOpt(
            "root_preconfig_password", secret=True, help="F5 root preconfig password"
        ),
        cfg.StrOpt(
            "admin_username", default="admin", help="F5 admin username (UI/API)"
        ),
        cfg.StrOpt(
            "admin_standard_password", secret=True, help="F5 admin standard password"
        ),
        cfg.StrOpt(
            "admin_preconfig_password",
            secret=True,
            help="F5 admin preconfig password",
        ),
    ]
    f5_grp = cfg.OptGroup("netdev_f5", title="F5 Credentials")
    cfg.CONF.register_group(f5_grp)
    cfg.CONF.register_opts(f5_opts, group=f5_grp)

    # Network device service accounts shared across device types
    common_opts = [
        cfg.StrOpt("service_account_a_username", help="Service account A username"),
        cfg.StrOpt(
            "service_account_a_password",
            secret=True,
            help="Service account A password",
        ),
        cfg.StrOpt("service_account_b_username", help="Service account B username"),
        cfg.StrOpt(
            "service_account_b_password",
            secret=True,
            help="Service account B password",
        ),
    ]
    common_grp = cfg.OptGroup("netdev_common", title="Network Device Service Accounts")
    cfg.CONF.register_group(common_grp)
    cfg.CONF.register_opts(common_opts, group=common_grp)


setup_conf()
