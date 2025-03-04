import argparse
import sys

from netinit.esxconfig import ESXConfig
from netinit.network_data import NetworkData

OLD_MGMT_PG = "Management Network"
OLD_VSWITCH = "vSwitch0"
NEW_MGMT_PG = "mgmt"
NEW_VSWITCH = "vSwitch22"


def main(json_file, dry_run):
    network_data = NetworkData.from_json_file(json_file)
    esx = ESXConfig(network_data, dry_run=dry_run)
    esx.clean_default_network_setup(OLD_MGMT_PG, OLD_VSWITCH)
    esx.configure_vswitch(
        uplink=esx.identify_uplink(), switch_name=NEW_VSWITCH, mtu=9000
    )

    esx.configure_portgroups()
    esx.add_default_mgmt_interface(NEW_MGMT_PG, NEW_VSWITCH)
    esx.configure_management_interface()
    esx.configure_default_route()
    esx.configure_requested_dns()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Network configuration script")
    parser.add_argument("json_file", help="Path to the JSON configuration file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without making any changes",
    )
    args = parser.parse_args()

    try:
        main(args.json_file, args.dry_run)
    except Exception as e:
        print(f"Error configuring network: {str(e)}")
        sys.exit(1)
