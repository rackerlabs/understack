from ironic.common import states
from ironic.drivers import base


class NoDeploy(base.DeployInterface):
    """Deploy interface that does nothing and succeeds.

    This interface allows Ironic to manage bare metal nodes for inventory,
    lifecycle tracking, and resource management without performing actual OS
    deployment operations.

    All methods succeed immediately without performing actual operations.
    Node state transitions occur as expected by Ironic's state machine.
    """

    def get_properties(self):
        """Return the properties of the interface.

        Returns:
            dict: Empty dictionary as no configuration is required.
        """
        return {}

    def validate(self, task):
        """Validate the driver-specific Node deployment info.

        This method intentionally accepts any node configuration for noop deploy.

        Args:
            task: A TaskManager instance containing the node to act on.
        """
        pass

    @base.deploy_step(priority=100)
    def deploy(self, task):
        """Perform a deployment to a node.

        This method returns None to indicate synchronous success without
        performing any actual deployment operations.

        Args:
            task: A TaskManager instance containing the node to act on.

        Returns:
            None: Indicates synchronous completion.
        """
        return None

    def tear_down(self, task):
        """Tear down a previous deployment on the task's node.

        Args:
            task: A TaskManager instance containing the node to act on.

        Returns:
            states.DELETED: Indicates the node is torn down.
        """
        return states.DELETED

    def prepare(self, task):
        """Prepare the deployment environment for the task's node.

        Args:
            task: A TaskManager instance containing the node to act on.
        """
        pass

    def clean_up(self, task):
        """Clean up the deployment environment for the task's node.

        Args:
            task: A TaskManager instance containing the node to act on.
        """
        pass

    def take_over(self, task):
        """Take over management of this task's node from a dead conductor.

        Args:
            task: A TaskManager instance containing the node to act on.
        """
        pass
