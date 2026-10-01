"""Management interface for PAN-OS (Palo Alto) appliances."""

from ironic.common import exception
from ironic.drivers import base
from ironic.drivers.modules import noop_mgmt
from oslo_log import log

LOG = log.getLogger(__name__)


class PanosManagement(noop_mgmt.NoopManagement):
    """Lifecycle steps for PAN-OS appliances.

    Boot device methods don't apply to a firewall, so those are inherited from
    NoopManagement.
    """

    @base.verify_step(priority=10)
    def setup_initial_configuration(self, task):
        """First-time setup of a factory-fresh appliance.

        Runs on enroll -> manageable. It must be idempotent and skip an
        appliance that has already been set up. Planned steps, committed once
        at the end:

        - management interface address, netmask, and gateway
        - remove the factory defaults that conflict with production use: the
          rule1 security rule, the trust and untrust zones, default-vwire, and
          the ethernet1/1 and ethernet1/2 config
        - jumbo frames
        - admin credentials, moving from the factory to the standard password
        - hostname from the node name
        """
        # TODO: implement. Left as a no-op so enrollment isn't blocked on it.
        LOG.warning(
            "[node:%s] PAN-OS initial configuration is not implemented yet, skipping",
            task.node.uuid,
        )

    @base.clean_step(priority=0, requires_ramdisk=False)
    def reset_to_factory_defaults(self, task):
        """Factory reset the appliance, then rerun initial configuration."""
        # TODO: implement. Fails rather than reporting a reset that didn't happen.
        raise exception.NodeCleaningFailure(
            node=task.node.uuid, reason="PAN-OS factory reset is not implemented yet"
        )

    @base.clean_step(priority=0, requires_ramdisk=False)
    def clear_configuration(self, task):
        """Remove tenant configuration, without a full factory reset.

        Removes security policies, NAT rules, and custom zones, interfaces,
        and routing. Keeps the management interface, admin credentials, and
        basic system settings.
        """
        # TODO: implement. Fails rather than reporting a clean that didn't happen.
        raise exception.NodeCleaningFailure(
            node=task.node.uuid,
            reason="PAN-OS configuration cleanup is not implemented yet",
        )
