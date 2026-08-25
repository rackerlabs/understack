import argparse
import os

from understack_workflows import helpers
from understack_workflows.dcx.client import DcxClient
from understack_workflows.dcx.enroll import enroll_from_dcx

DCX_TOKEN_ENV = "DCX_TOKEN"  # noqa: S105 (env var name, not a secret)
DCX_API_ENV = "DCX_API"


def main() -> None:
    """Create netdev baremetal nodes from DCX inventory data.

    For each device number, fetch its switch ports and location from DCX, then
    create (or idempotently reconcile) a netdev Ironic node named
    ``<name-prefix>-<device_number>`` with a baremetal port per data (Public)
    port. Requires the DCX auth token in the ``DCX_TOKEN`` environment variable,
    the DCX API base URL via ``--dcx-api`` (or the ``DCX_API`` environment
    variable), and (for a real run) ``OS_CLOUD`` set for the Ironic connection.
    """
    helpers.setup_logger()
    args = argument_parser().parse_args()

    token = os.getenv(DCX_TOKEN_ENV)
    if not token:
        raise SystemExit(f"{DCX_TOKEN_ENV} environment variable must be set")

    api_url = args.dcx_api or os.getenv(DCX_API_ENV)
    if not api_url:
        raise SystemExit(f"DCX API base URL must be set via --dcx-api or {DCX_API_ENV}")

    client = DcxClient(auth_token=token, api_url=api_url)

    for device_number in args.device_number:
        enroll_from_dcx(
            client=client,
            device_number=device_number,
            name_prefix=args.name_prefix,
            physical_network=args.physical_network,
            resource_class=args.resource_class,
            dry_run=args.dry_run,
        )


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Enroll netdev baremetal nodes from DCX inventory data",
    )
    parser.add_argument(
        "device_number",
        nargs="+",
        help="One or more DCX device numbers (external_cmdb_id)",
    )
    parser.add_argument(
        "--name-prefix",
        required=True,
        help="Node name prefix, e.g. Appliance -> Appliance-<device_number>",
    )
    parser.add_argument(
        "--physical-network",
        required=False,
        default=None,
        help="Override the physical_network (default: derived from the switches)",
    )
    parser.add_argument(
        "--resource-class",
        required=False,
        default=None,
        help="Ironic resource class (default: lowercased --name-prefix)",
    )
    parser.add_argument(
        "--dcx-api",
        required=False,
        default=None,
        help=f"DCX API base URL (falls back to the {DCX_API_ENV} env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and build the payload but do not touch Ironic",
    )
    return parser


if __name__ == "__main__":
    main()
