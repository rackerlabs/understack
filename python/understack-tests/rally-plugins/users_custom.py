import time

from rally.common import logging
from rally.task import context
from rally_openstack.task.contexts.keystone import users

LOG = logging.getLogger(__name__)


@context.configure(name="users_custom", order=100)
class UsersCustom(users.UserGenerator):
    """Custom users context that sleeps 60s after creating projects."""

    def setup(self):
        LOG.debug("UsersCustom: setup starting...")

        # Call the original setup (creates projects and users normally)
        super().setup()

        # Add the custom behavior to sleep allowing fofor Nautobot to sync
        self.context["users_override_note"] = "Sleep for Nautobot sync"

        # After we create a project, sleep for 60 seconds, allowing some
        # time for it to sync to Nautobot
        LOG.debug("UsersCustom: sleeping for 60 seconds...")
        time.sleep(60)

        LOG.debug("UsersCustom: completed")

    def cleanup(self):
        # Run the default cleanup
        super().cleanup()
