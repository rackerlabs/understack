import argparse
import os

from understack_workflows import helpers
from understack_workflows.netdev_reconciler import DEFAULT_RESOURCE_CLASS
from understack_workflows.netdev_reconciler import build_netdev_ports  # noqa: F401
from understack_workflows.netdev_reconciler import enroll
from understack_workflows.netdev_reconciler import parse_ports_arg


def main() -> None:
    """Create a netdev baremetal node, its ports, and make it available.

    Thin CLI over the shared netdev enrollment engine
    (``understack_workflows.netdev_reconciler``). Re-running with the same
    parameters is safe: an existing node with the same name is reused (and
    updated), existing ports are matched by their label-derived name
    (node_name:label) and updated in place, and provision-state transitions are
    only performed when needed.

    Any number of ports may be supplied via --ports. Each port must include a
    stable label; changing, removing, or renaming labels is a manual operation.
    """
    helpers.setup_logger()
    args = argument_parser().parse_args()

    enroll(
        name=args.name,
        physical_network=args.physical_network,
        ports=parse_ports_arg(args.ports),
        external_cmdb_id=args.external_cmdb_id,
        resource_class=args.resource_class,
    )


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Run the netdev enroll workflow",
    )
    parser.add_argument("--name", required=True, help="Ironic node name")
    parser.add_argument(
        "--physical-network",
        required=True,
        help="Port physical_network",
    )
    parser.add_argument(
        "--ports",
        required=True,
        help=(
            "JSON array of ports with stable labels, e.g. "
            '[{"label": "port1", "mac": "..", "switch": "..", "intf": ".."}]. '
            'Optional per-port "switch_id" (real switch MAC) overrides the '
            "00:00:00:00:00:00 placeholder. Change/remove/rename labels manually."
        ),
    )
    parser.add_argument(
        "--external-cmdb-id",
        type=helpers.int_or_str,
        required=False,
        default="",
        help="CMDB ID",
    )
    parser.add_argument(
        "--resource-class",
        required=False,
        default=DEFAULT_RESOURCE_CLASS,
        help="Ironic resource class",
    )
    return parser


if __name__ == "__main__":
    main()
