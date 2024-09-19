import os
import requests
import sushy
import json
from urllib import parse as urlparse
import urllib3
import argparse
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog=os.path.basename(__file__), description="Update BMC firmware")
    parser.add_argument("--host", required=True, help="The address of the BMC interface")
    parser.add_argument("--firmware-url", required=True, help="URL of firmware")

    args = parser.parse_args()
    host = args.host
    firmware_url = args.firmware_url
    username = os.environ["BMC_USERNAME"]
    password = os.environ["BMC_PASSWORD"]

    logger.info("Fetching BMC update service ...")

    authn = sushy.auth.SessionOrBasicAuth(username, password)
    c = sushy.Sushy(f"https://{host}/redfish/v1/", verify=False, auth=authn)
    updsvc = c.get_update_service()

    filename = firmware_url.split("/")[-1]

    headers = {
        "Cookie": f"sessionKey={c._conn._auth._session_key}",
        "Content-Type": "multipart/form-data",
    }

    update_data = {"UpdateRepository": True, "UpdateTarget": True, "ETag": "atag", "Section": 0}

    upd_url = urlparse.urljoin(c._conn._url, updsvc.http_push_uri)

    logger.info(f"Fetching firmware from {firmware_url}")
    logger.info(f"Uploading firmware to {upd_url}")

    task = None
    try:
        with requests.get(firmware_url, stream=True) as r:
            r.raise_for_status()
            multipart = [
                ("sessionKey", c._conn._auth._session_key),
                ("parameters", json.dumps(update_data)),
                ("file", (filename, r.raw, "application/octet-stream")),
            ]
            rsp = c._conn._session.post(upd_url, files=multipart, verify=False, headers=headers)
            logger.info(rsp.json())
    except Exception as e:
        logger.error(e)

    logger.info("Firmware update complete.")
