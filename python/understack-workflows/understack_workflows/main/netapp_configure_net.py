import argparse
import json
import logging
import uuid
from dataclasses import dataclass

from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.nautobot import Nautobot
from understack_workflows.netapp_manager import NetappIPInterfaceConfig
from understack_workflows.netapp_manager import NetAppManager

logger = setup_logger(__name__, level=logging.INFO)

# GraphQL query to retrieve virtual machine network information as specified in
# requirements
VIRTUAL_MACHINES_QUERY = (
    "query ($device_names: [String]){virtual_machines(name: $device_names) "
    "{interfaces { name ip_addresses{ address } tagged_vlans { vid }}}}"
)


@dataclass
class InterfaceInfo:
    name: str
    address: str
    vlan: int

    @classmethod
    def from_graphql_interface(cls, interface_data):
        """Create InterfaceInfo from GraphQL interface data with validation.

        Args:
            interface_data: GraphQL interface data containing name,
                            ip_addresses, and tagged_vlans

        Returns:
            InterfaceInfo: Validated interface information

        Raises:
            ValueError: If interface has zero or multiple IP addresses or VLANs
        """
        name = interface_data.get("name", "")
        ip_addresses = interface_data.get("ip_addresses", [])
        tagged_vlans = interface_data.get("tagged_vlans", [])

        # Validate exactly one IP address
        if len(ip_addresses) == 0:
            raise ValueError(f"Interface '{name}' has no IP addresses")
        elif len(ip_addresses) > 1:
            raise ValueError(
                f"Interface '{name}' has multiple IP addresses:"
                f" {[ip['address'] for ip in ip_addresses]}"
            )

        # Validate exactly one tagged VLAN
        if len(tagged_vlans) == 0:
            raise ValueError(f"Interface '{name}' has no tagged VLANs")
        elif len(tagged_vlans) > 1:
            raise ValueError(
                f"Interface '{name}' has multiple tagged VLANs:"
                f" {[vlan['vid'] for vlan in tagged_vlans]}"
            )

        address = ip_addresses[0]["address"]
        vlan = tagged_vlans[0]["vid"]

        return cls(name=name, address=address, vlan=vlan)


@dataclass
class VirtualMachineNetworkInfo:
    interfaces: list[InterfaceInfo]

    @classmethod
    def from_graphql_vm(cls, vm_data):
        """Create VirtualMachineNetworkInfo from GraphQL virtual machine data.

        Args:
            vm_data: GraphQL virtual machine data containing interfaces

        Returns:
            VirtualMachineNetworkInfo: Validated virtual machine network information

        Raises:
            ValueError: If any interface validation fails
        """
        interfaces = []
        for interface_data in vm_data.get("interfaces", []):
            interface_info = InterfaceInfo.from_graphql_interface(interface_data)
            interfaces.append(interface_info)

        return cls(interfaces=interfaces)


def validate_and_normalize_uuid(value: str) -> str:
    """Validate that the input is a valid UUID and normalize it by removing dashes.

    Args:
        value: String that should be a valid UUID (with or without dashes)

    Returns:
        str: UUID string with dashes removed

    Raises:
        argparse.ArgumentTypeError: If the input is not a valid UUID
    """
    try:
        # Try to parse as UUID - this handles both formats (with and without dashes)
        uuid_obj = uuid.UUID(value)
        # Return the hex string without dashes
        return uuid_obj.hex
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Invalid UUID format: {value}") from e


def argument_parser():
    """Parse command line arguments for netapp network configuration."""
    parser = argparse.ArgumentParser(
        description="Query Nautobot for SVM network configuration and create "
        "NetApp interfaces based on project ID",
    )

    # Add required project_id argument with UUID validation
    parser.add_argument(
        "--project-id",
        type=validate_and_normalize_uuid,
        required=True,
        help="OpenStack project ID (UUID) to query for SVM configuration",
    )

    parser.add_argument(
        "--netapp-config-path",
        type=str,
        default="/etc/netapp/netapp_nvme.conf",
        help="Path to NetApp config with credentials "
        "(default: /etc/netapp/netapp_nvme.conf)",
    )

    # Add Nautobot connection arguments using the helper
    return parser_nautobot_args(parser)


def construct_device_name(project_id: str) -> str:
    """Construct device name from project_id using format 'os-{project_id}'.

    Args:
        project_id: The OpenStack project ID

    Returns:
        str: The constructed device name in format 'os-{project_id}'
    """
    return f"os-{project_id}"


def execute_graphql_query(nautobot_client: Nautobot, project_id: str) -> dict:
    """Execute GraphQL query to retrieve virtual machine network information.

    Args:
        nautobot_client: Nautobot API client instance
        project_id: OpenStack project ID to query for

    Returns:
        dict: GraphQL query response data

    Raises:
        Exception: If GraphQL query fails or returns errors
    """
    # Construct device name and prepare variables
    device_name = construct_device_name(project_id)
    variables = {"device_names": [device_name]}

    logger.debug("Executing GraphQL query for device: %s", device_name)
    logger.debug("Query variables: %s", variables)

    # Execute the GraphQL query
    try:
        result = nautobot_client.session.graphql.query(
            query=VIRTUAL_MACHINES_QUERY, variables=variables
        )
    except Exception as e:
        logger.error("Failed to execute GraphQL query: %s", e)
        raise Exception(f"GraphQL query execution failed: {e}") from e

    # Check for GraphQL errors in response
    if not result.json:
        raise Exception("GraphQL query returned no data")

    if result.json.get("errors"):
        error_messages = [
            error.get("message", str(error)) for error in result.json["errors"]
        ]
        error_details = "; ".join(error_messages)
        logger.error("GraphQL query returned errors: %s", error_details)
        raise Exception(f"GraphQL query failed with errors: {error_details}")

    # Log successful query execution
    data = result.json.get("data", {})
    vm_count = len(data.get("virtual_machines", []))
    logger.info(
        "GraphQL query successful. Found %s virtual machine(s) for device: %s",
        vm_count,
        device_name,
    )

    return result.json


def validate_and_transform_response(
    graphql_response: dict,
) -> list[VirtualMachineNetworkInfo]:
    """Validate and transform GraphQL response into structured data objects.

    Args:
        graphql_response: Complete GraphQL response containing data and
            potential errors

    Returns:
        list[VirtualMachineNetworkInfo]: List of validated SVM network
            information

    Raises:
        ValueError: If any interface validation fails
    """
    data = graphql_response.get("data", {})
    virtual_machines = data.get("virtual_machines", [])

    if not virtual_machines:
        logger.warning("No virtual machines found in GraphQL response")
        return []

    vm_network_infos = []

    for vm_data in virtual_machines:
        try:
            vm_network_info = VirtualMachineNetworkInfo.from_graphql_vm(vm_data)
            vm_network_infos.append(vm_network_info)
            logger.debug(
                "Successfully validated VM with %s interfaces",
                len(vm_network_info.interfaces),
            )
        except ValueError as e:
            logger.error("Interface validation failed: %s", e)
            raise ValueError(f"Data validation error: {e}") from e

    logger.info("Successfully validated %s virtual machine(s)", len(vm_network_infos))
    return vm_network_infos


def do_action(
    nautobot_client: Nautobot, netapp_manager: NetAppManager, project_id: str
) -> tuple[dict, list[VirtualMachineNetworkInfo]]:
    """Execute main GraphQL query, process results, and create NetApp interfaces.

    This function orchestrates the workflow by:
    1. Executing GraphQL query using constructed device name
    2. Processing and validating query results
    3. Creating NetApp LIF interfaces using the validated data
    4. Returning structured data objects
    5. Handling all error scenarios with appropriate exit codes

    Args:
        nautobot_client: Nautobot API client instance
        netapp_manager: NetAppManager API client for creating LIF interfaces
        project_id: OpenStack project ID to query for

    Returns:
        tuple: (raw_graphql_response, validated_vm_network_infos)
            - raw_graphql_response: Complete GraphQL response as dict
            - validated_vm_network_infos: List of VirtualMachineNetworkInfo
                objects

    Raises:
        SystemExit: With appropriate exit codes for different error scenarios:
            - Exit code 1: Connection errors
            - Exit code 2: GraphQL query errors
            - Exit code 3: Data validation errors
    """
    try:
        # Execute GraphQL query using constructed device name
        logger.info(
            "Querying Nautobot for SVM network configuration (project_id: %s)",
            project_id,
        )
        raw_response = execute_graphql_query(nautobot_client, project_id)

        # Process and validate query results
        logger.debug("Processing and validating GraphQL response")
        validated_data = validate_and_transform_response(raw_response)

        # Log successful completion
        device_name = construct_device_name(project_id)
        if validated_data:
            total_interfaces = sum(len(vm.interfaces) for vm in validated_data)
            logger.info(
                "Successfully processed %d virtual machine(s) with %d total "
                "interfaces for device: %s",
                len(validated_data),
                total_interfaces,
                device_name,
            )
        else:
            logger.warning("No virtual machines found for device: %s", device_name)

    except ValueError as e:
        # Handle data validation error scenarios with exit code 3
        logger.error("Data validation failed: %s", e)
        raise SystemExit(3) from e

    except Exception as e:
        error_msg = str(e)

        # Handle GraphQL-specific error scenarios with exit code 2
        if "graphql" in error_msg.lower() or "query" in error_msg.lower():
            logger.error("GraphQL query failed: %s", error_msg)
            raise SystemExit(2) from e

        # Handle other unexpected errors with exit code 2 (query-related)
        else:
            logger.error("Nautobot error: %s", error_msg)
            raise SystemExit(2) from e

    if validated_data:
        netapp_create_interfaces(netapp_manager, validated_data[0], project_id)

    # Return structured data objects
    return raw_response, validated_data


def netapp_create_interfaces(
    mgr: NetAppManager,
    nautobot_response: VirtualMachineNetworkInfo,
    project_id: str,
) -> None:
    """Create NetApp LIF interfaces based on Nautobot VM network configuration.

    This function converts the validated Nautobot response into NetApp interface
    configurations and creates the corresponding LIF (Logical Interface) on the
    NetApp storage system.

    Args:
        mgr: NetAppManager instance for creating LIF interfaces
        nautobot_response: Validated virtual machine network information from
            Nautobot
        project_id: OpenStack project ID for logging and context

    Returns:
        None

    Raises:
        Exception: If SVM for the project is not found
        NetAppRestError: If LIF creation fails on the NetApp system
    """
    configs = NetappIPInterfaceConfig.from_nautobot_response(nautobot_response)
    for interface_config in configs:
        logger.info("Creating LIF %s for project %s", interface_config.name, project_id)
        mgr.create_lif(project_id, interface_config)
    return


def format_and_display_output(
    raw_response: dict, structured_data: list[VirtualMachineNetworkInfo]
) -> None:
    """Format and display query results with appropriate logging.

    This function handles:
    1. Printing raw GraphQL response as JSON to standard output
    2. Providing access to structured data objects for programmatic use
    3. Handling empty results case (no virtual machines found)
    4. Adding appropriate logging for successful operations

    Args:
        raw_response: Complete GraphQL response as dict
        structured_data: List of validated VirtualMachineNetworkInfo objects
    """
    # Print raw GraphQL response as JSON to standard output
    print(json.dumps(raw_response, indent=2))

    # Handle empty results case
    if not structured_data:
        logger.warning("No virtual machines found for the given project ID")
        return

    # Log successful operations with summary information
    total_vms = len(structured_data)
    total_interfaces = sum(len(vm.interfaces) for vm in structured_data)

    logger.info(
        "Successfully retrieved network configuration for %s virtual machine(s)",
        total_vms,
    )
    logger.info("Total interfaces found: %s", total_interfaces)

    # Log detailed interface information at debug level
    for i, vm in enumerate(structured_data):
        logger.debug(
            "SVM/Virtual machine %d has {len(vm.interfaces)} interface(s):",
            i + 1,
        )
        for interface in vm.interfaces:
            logger.debug(
                "  - Interface '%s': %s (VLAN %s)",
                interface.name,
                interface.address,
                interface.vlan,
            )


def main():
    """Main entry point for the netapp network configuration script.

    This function follows the established pattern by:
    1. Parsing command line arguments using argument_parser()
    2. Establishing Nautobot connection using parsed arguments
    3. Initializing NetAppManager with configuration path
    4. Calling do_action() with appropriate parameters to query Nautobot and
       create NetApp interfaces
    5. Handling return codes and exit appropriately

    Returns:
        int: Exit code (0 for success, non-zero for errors)
            - 0: Success - interfaces created successfully
            - 1: Connection errors, authentication failures, initialization
                 errors
            - 2: GraphQL query errors, syntax errors, execution errors
            - 3: Data validation errors, interface validation failures
    """
    try:
        # Parse command line arguments using argument_parser()
        args = argument_parser().parse_args()

        # Get nautobot token with credential fallback
        nb_token = args.nautobot_token or credential("nb-token", "token")

        # Establish Nautobot connection using parsed arguments
        logger.info("Connecting to Nautobot at: %s", args.nautobot_url)
        nautobot_client = Nautobot(args.nautobot_url, nb_token, logger=logger)
        netapp_manager = NetAppManager(args.netapp_config_path)

        # Call do_action() with appropriate parameters
        raw_response, structured_data = do_action(
            nautobot_client, netapp_manager, args.project_id
        )

        # Format and display output
        format_and_display_output(raw_response, structured_data)

        # Return success exit code
        logger.info("Script completed successfully")
        return 0

    except SystemExit as e:
        # Handle exit codes from do_action() - these are already logged
        return e.code if e.code is not None else 1

    except Exception as e:
        # Handle connection errors and other unexpected errors with exit code 1
        logger.error("Connection or initialization error: %s", e)
        return 1


if __name__ == "__main__":
    exit(main())
