"""Ironic runbook plugin constants.

Runtime configuration comes from :class:`openstack_sync.hooks.framework.HookConfig`,
built from the ``IRONIC_RUNBOOK`` env prefix the Helm chart injects.
"""

from __future__ import annotations

#: The Ironic API microversion this plugin requires. It is the first with runbook
#: descriptions and the traits sub-resource, both of which the CRD exposes.
RUNBOOK_MICROVERSION = "1.112"

#: Env prefix the Helm chart uses for this plugin's variables.
ENV_PREFIX = "IRONIC_RUNBOOK"

#: shell-operator binding label for the CRD watch.
BINDING_NAME = "ironic-runbooks"
