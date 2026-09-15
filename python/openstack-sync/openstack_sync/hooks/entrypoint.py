"""Shell-operator entrypoint handling for OpenStack sync hooks."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from collections.abc import Sequence
from typing import Any

LOG = logging.getLogger("openstack_sync.hooks.framework")


def run_hook(
    build_config: Callable[[], dict[str, Any]],
    run: Callable[[list[dict[str, Any]]], int],
    *,
    argv: Sequence[str],
    configure_logging: Callable[[], None],
    read_binding_context: Callable[[], list[dict[str, Any]]],
    emit: Callable[[str], None] = print,
) -> int:
    """Handle the shell-operator calling convention shared by every hook.

    ``--config`` prints the hook config and exits; otherwise the binding
    context is read and handed to *run*. An empty or absent binding context is
    not an error -- shell-operator invokes hooks with no work to do.
    """
    if len(argv) > 1 and argv[1] == "--config":
        emit(json.dumps(build_config(), indent=2))
        return 0

    configure_logging()

    try:
        contexts = read_binding_context()
    except ValueError as exc:
        LOG.error("failed to parse binding context: %s", exc)
        return 1

    if not contexts:
        return 0

    try:
        return run(contexts)
    except Exception as exc:  # noqa: BLE001
        # Type and traceback, not just the message: several builtins stringify
        # to something unusable on their own, a KeyError to nothing but the
        # missing key. This is the hook's last line, so whatever it omits is
        # lost.
        LOG.error("hook failed: %s: %s", type(exc).__name__, exc, exc_info=True)
        return 1
