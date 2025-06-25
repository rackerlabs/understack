import time
from sushy import ResetType
from understack_workflows.bmc import Bmc
from understack_workflows.helpers import setup_logger

import logging

logger = setup_logger(__name__)
# sushy is really verbose by default:
logging.getLogger("sushy.main").setLevel(logging.INFO)
logging.getLogger("sushy.connector").setLevel(logging.INFO)
logging.getLogger("sushy.resources.base").setLevel(logging.INFO)


DRAC_MANAGER_URL = "/redfish/v1/Managers/iDRAC.Embedded.1/"
RESET_URL = "/redfish/v1/Managers/iDRAC.Embedded.1/Actions/Manager.Reset"
SIMPLE_UPDATE_URL = "/redfish/v1/UpdateService/Actions/UpdateService.SimpleUpdate"


def update_firmware_if_required(bmc: Bmc, required_version: str, image_url: str):
    """Update firmare on an iDRAC9, unless required_version is already running.

    >>> update_firmware_if_required(
            bmc=bmc_for_ip_address("10.15.149.16"),
            required_version="7.20.30.00",
            image_url="http://148.62.102.2/iDRAC9_7.20.30.00_A00.d9"
        )
    """

    sushy = bmc.sushy()

    if running_required_version(sushy, required_version):
        return

    install_firmware(bmc, image_url)
    wait_for_reboot(bmc, required_version)


def running_required_version(sushy, required_version: str) -> bool:
    running_version = sushy.get_manager().firmware_version
    if running_version == required_version:
        logger.info(
            "iDRAC is running required firmware %s, no update required",
            required_version,
        )
        return True
    else:
        logger.debug(
            "iDRAC currently running version %s, need update to %s",
            running_version,
            required_version,
        )
        return False


def install_firmware(bmc, image_url):
    payload = {"ImageURI": image_url}
    logger.info("Performing Simple Update of DRAC with %s", image_url)
    _, headers = bmc.redfish_request_with_headers(
        path=SIMPLE_UPDATE_URL, method="POST", payload=payload
    )
    job_url = headers.get("Location")
    wait_for_job_completion(bmc, job_url)


def reboot_drac(bmc):
    logger.info("Rebooting DRAC into updated firmware")
    bmc.sushy().get_manager().reset_manager(ResetType.GRACEFUL_RESTART)
    logger.debug("Reboot request issued")


def wait_for_job_completion(bmc, uri, timeout_secs=300):
    deadline = time.monotonic() + timeout_secs
    logger.debug("Waiting for job %s to complete", uri)
    job_status = None
    while time.monotonic() < deadline:
        try:
            job_status = bmc.redfish_request(uri)

            percent_complete = job_status.get("PercentComplete")
            if percent_complete:
                logger.debug("Job is %s percent complete", percent_complete)

            if percent_complete == 100:
                return

            if job_status.get("JobState") == "RebootFailed":
                return reboot_drac(bmc)

        except Exception as e:
            logger.info("Failed to get job status %s: %s", uri, e)

        time.sleep(10)
    raise Exception(
        f"Giving up on Update Job {uri} it is not complete after "
        f"{timeout_secs} secs: {job_status}, unsure whether updated succeeded."
    )


def wait_for_reboot(bmc, required_version, timeout_secs=600):
    logger.debug("Waiting for BMC to come back after reset")

    deadline = time.monotonic() + timeout_secs
    while time.monotonic() < deadline:
        time.sleep(30)

        try:
            running_version = bmc.sushy().get_manager().firmware_version
            if running_version == required_version:
                logger.info("Firmware update successful")
                return
            else:
                raise RuntimeError(
                    "Bad firware update: after reboot, {running_version=}"
                )
        except Exception as e:
            logger.debug("BMC Not yet avaiable after reset: %s", e)
            pass

    raise Exception(f"BMC Update failed: Given up after {timeout_secs}sec")
