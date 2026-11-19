"""Power interface for network devices."""

from ironic.drivers.modules import fake


class NetdevPower(fake.FakePower):
    """Fake power that opts out of power sync, so last_error is kept.

    See https://bugs.launchpad.net/ironic/+bug/2175085.
    """

    def supports_power_sync(self, task):
        return False
