import argparse
import json

from understack_workflows import helpers
from understack_workflows import ironic_node
from understack_workflows.ironic.client import IronicClient


def main() -> None:
    """Run Ironic runbooks in order against an enrolled node."""
    helpers.setup_logger()
    args = argument_parser().parse_args()
    node = IronicClient().get_node(args.node)
    ironic_node.run_runbooks_standalone(node, args.runbooks)


def parse_runbooks(value: str) -> list[str]:
    """Parse an ordered JSON array of nonempty runbook names or UUIDs."""
    try:
        runbooks = json.loads(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Expected a JSON array of runbook names or UUIDs"
        ) from exc
    if not isinstance(runbooks, list) or any(
        not isinstance(runbook, str) or not runbook.strip() for runbook in runbooks
    ):
        raise argparse.ArgumentTypeError(
            "Expected a JSON array of nonempty runbook names or UUIDs"
        )
    return runbooks


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apply-node-runbook",
        description="Run Ironic runbooks in order against an enrolled node.",
    )
    parser.add_argument(
        "--runbooks",
        type=parse_runbooks,
        required=True,
        help=(
            "JSON array of runbook names or UUIDs to run in order, e.g. "
            "'[\"bmc-configure-snmpv3-user\"]'"
        ),
    )
    parser.add_argument(
        "--node",
        required=True,
        help="Node name or UUID",
    )
    return parser


if __name__ == "__main__":
    main()
