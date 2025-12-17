from understack_workflows.bmc import Bmc
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)


def bmc_power_on(bmc: Bmc):
    """Make a redfish call to switch on the power to the system."""
    bmc.redfish_request(
        bmc.system_path + "/Actions/ComputerSystem.Reset",
        payload={"ResetType": "On"},
        method="POST",
    )
