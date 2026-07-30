"""Shared connection context: kube context/namespace/pods and OpenStack cloud target.

Every subcommand prints a banner describing what it's actually talking to,
modeled on print_connection_banner() in scripts/cleanup_dead_ovn_ha_chassis.py.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from us_net import osclient


@dataclass
class ConnectionContext:
    kube_context: str | None
    namespace: str
    nb_pod: str
    sb_pod: str
    os_cloud: str | None

    def kubectl_base(self) -> list[str]:
        cmd = ["kubectl"]
        if self.kube_context:
            cmd += ["--context", self.kube_context]
        return cmd


def resolve_kube_context(kube_context: str | None) -> str:
    """Return the kube context that will actually be used."""
    if kube_context:
        return kube_context
    result = subprocess.run(
        ["kubectl", "config", "current-context"], capture_output=True, text=True
    )
    return result.stdout.strip() or "(unknown)"


def print_connection_banner(
    ctx: ConnectionContext, include_openstack: bool = False
) -> None:
    """Print what cluster/namespace/pods/cloud this invocation is targeting."""
    print("=" * 64)
    print("kubectl-us-net -- target environment")
    print("=" * 64)
    print(f"  Kubernetes context : {resolve_kube_context(ctx.kube_context)}")
    print(f"  OVN namespace/pods : {ctx.namespace} (nb={ctx.nb_pod}, sb={ctx.sb_pod})")
    if include_openstack:
        cloud_label = ctx.os_cloud or "(default via OS_CLOUD / clouds.yaml)"
        print(f"  OpenStack cloud    : {cloud_label}")
        for label, val in osclient.describe_target(ctx.os_cloud):
            print(f"    {label:<16} : {val}")
    print("=" * 64)
    print(flush=True)
