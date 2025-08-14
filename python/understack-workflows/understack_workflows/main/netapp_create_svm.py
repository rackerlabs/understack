import argparse
import configparser
import os

import argparse
import requests
import urllib3

# Per your request, import setup_logger and initialize it
# This assumes 'understack_workflows' is an available package in your environment.
try:
    from understack_workflows.helpers import setup_logger

    logger = setup_logger(__name__)
except ImportError:
    # Fallback to standard logging if the custom helper is not found
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)
    logger.warning(
        "Could not import 'setup_logger' from 'understack_workflows.helpers'. Falling back to standard logging."
    )


# Suppress warnings for unverified HTTPS requests, common in lab environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_ontap_config(config_path="/etc/netapp/config.ini"):
    """
    Reads ONTAP connection details from a specified INI configuration file.
    """
    if not os.path.exists(config_path):
        logger.error(f"Configuration file not found at {config_path}")
        exit(1)

    config = configparser.ConfigParser()
    config.read(config_path)

    try:
        logger.debug(
            f"Reading configuration from section [netapp_nvme] in {config_path}"
        )
        hostname = config.get("netapp_nvme", "netapp_server_hostname")
        login = config.get("netapp_nvme", "netapp_login")
        password = config.get("netapp_nvme", "netapp_password")
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        logger.error(f"Missing required configuration in {config_path}. Details: {e}")
        exit(1)

    return hostname, login, password


def parse_size_to_bytes(size_str):
    """
    Parses a human-readable size string (e.g., '1TB', '500GB') and returns the equivalent in bytes.
    """
    size_str = size_str.upper().strip()
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}

    numeric_part_str = "".join(filter(str.isdigit, size_str))
    unit_part = "".join(filter(str.isalpha, size_str))

    if not numeric_part_str or not unit_part:
        raise ValueError(
            f"Invalid size format: '{size_str}'. Must include a number and a unit (e.g., '1024GB')."
        )

    if not unit_part.endswith("B"):
        unit_part += "B"

    if unit_part not in units:
        raise ValueError(
            f"Unsupported size unit: '{unit_part}'. Supported units are TB, GB, MB, KB."
        )

    return int(numeric_part_str) * units[unit_part]


def ontap_rest_call(method, url, auth, json_data=None):
    """
    Makes a generic REST API call to the ONTAP system.
    """
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    logger.debug(f"Making REST call: {method} {url}")
    if json_data:
        logger.debug(f"Request payload: {json_data}")

    try:
        response = requests.request(
            method, url, headers=headers, auth=auth, json=json_data, verify=False
        )
        response.raise_for_status()
        if response.content:
            return response.json()
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during API call to {url}: {e}")
        if hasattr(e, "response") and e.response is not None:
            logger.error(f"Response content: {e.response.text}")
        exit(1)


def create_svm(base_url, auth, svm_name):
    """Creates a new Storage Virtual Machine (SVM)."""
    logger.info(f"Creating SVM: {svm_name}...")
    url = f"{base_url}/svm/svms"
    payload = {"name": svm_name}
    ontap_rest_call("POST", url, auth, json_data=payload)
    logger.info(f"SVM {svm_name} created successfully.")


def allow_nvme_protocol_on_svm(base_url, auth, svm_name):
    """Modifies an SVM to allow the NVMe protocol."""
    logger.info(f"Modifying SVM {svm_name} to allow NVMe protocol...")
    get_url = f"{base_url}/svm/svms?name={svm_name}"
    svm_data = ontap_rest_call("GET", get_url, auth)

    if not svm_data or not svm_data.get("records"):
        logger.error(f"Could not find SVM '{svm_name}' to modify.")
        exit(1)

    svm_uuid = svm_data["records"][0]["uuid"]
    logger.debug(f"Found UUID for SVM '{svm_name}': {svm_uuid}")

    modify_url = f"{base_url}/svm/svms/{svm_uuid}"
    payload = {"protocols": ["nvme"]}
    ontap_rest_call("PATCH", modify_url, auth, json_data=payload)
    logger.info(f"SVM {svm_name} successfully modified to allow NVMe.")


def create_volume(base_url, auth, svm_name, volume_size_str, aggregate_name):
    """Creates a new volume within a specific SVM and aggregate."""
    volume_name = f"vol_{svm_name}"
    logger.info(
        f"Creating volume '{volume_name}' with size {volume_size_str} on aggregate '{aggregate_name}'..."
    )

    try:
        size_in_bytes = parse_size_to_bytes(volume_size_str)
        logger.debug(f"Parsed size '{volume_size_str}' to {size_in_bytes} bytes.")
    except ValueError as e:
        logger.error(f"Invalid volume size: {e}")
        exit(1)

    url = f"{base_url}/storage/volumes"
    payload = {
        "svm": {"name": svm_name},
        "name": volume_name,
        "aggregates": [{"name": aggregate_name}],
        "size": size_in_bytes,
        "space": {"guarantee": "none"},
    }
    ontap_rest_call("POST", url, auth, json_data=payload)
    logger.info(f"Volume '{volume_name}' created successfully.")


def argument_parser():
    parser = argparse.ArgumentParser(
        description="NetApp ONTAP SVM and Volume Creator via REST API",
        prog=os.path.basename(__file__),
    )
    parser.add_argument(
        "--svm_name", required=True, help="Name of the SVM to be created"
    )
    parser.add_argument(
        "--volume_size", required=True, help="Size of the volume (e.g., '1TB', '500GB')"
    )
    parser.add_argument(
        "--aggregate_name", required=True, help="Name of the aggregate for the volume"
    )
    parser.add_argument(
        "--config_file",
        default="/etc/netapp/config.ini",
        help="Path to the configuration file",
    )

    return parser


def main():
    """
    Main function to orchestrate the SVM and volume creation process.
    """
    args = argument_parser().parse_args()
    logger.info("Starting ONTAP SVM and Volume creation workflow.")

    hostname, login, password = get_ontap_config(args.config_file)
    base_url = f"https://{hostname}/api"
    auth = (login, password)

    do_action(base_url, auth, args)
    logger.info("All operations completed successfully!")


def do_action(base_url, auth, args):
    create_svm(base_url, auth, args.svm_name)
    allow_nvme_protocol_on_svm(base_url, auth, args.svm_name)
    logger.info("NVMe service is enabled by setting the allowed protocol on the SVM.")
    create_volume(base_url, auth, args.svm_name, args.volume_size, args.aggregate_name)


if __name__ == "__main__":
    main()
