import json
from dataclasses import asdict
from pathlib import Path

import jsonschema
import nautobot.extras.jobs
import requests
from nautobot.apps.jobs import Job
from nautobot.apps.jobs import StringVar

from .ironic.network_data import Network
from .ironic.network_data import NetworkInfo
from .ironic.network_data import NetworkRoute
from .ironic.network_data import PhysicalNic
from .ironic.network_data import Service
from .ironic.node_configuration import IronicNodeConfiguration

# Nautobot Job grouping/namespace
name = "Rackspace"

logger = nautobot.extras.jobs.get_task_logger(__name__)


class IronicDevicePush(Job):
    class Meta:
        """Metadata about this Job"""

        name = "Nautobot => Ironic"
        description = "Push the Device information into Ironic API"
        dryrun_default = False

    device = StringVar(max_length=64, required=True, description="Device name")

    def run(self, *args, **kwargs):
        device = kwargs["device"]
        logger.info(f"Pushing device {device} to Ironic.")

        configuration_data = IronicNodeConfiguration()
        # configuration_data.chassis_uuid = "abcdefab-abcd-abcd-abcd-14c2a8a3e0a2"
        configuration_data.chassis_uuid = None
        configuration_data.uuid = "ffffffff-abcd-abcd-abcd-14c2a8a3e0a2"
        configuration_data.name = device
        id_of_exnet_interface = "c48137a7-0eec-45a7-a766-14c2a8a3e0a2"
        exnet_ip = "192.168.40.3"
        exnet_netmask = "255.255.255.0"
        configuration_data.conductor_group = None
        configuration_data.driver = 'redfish'
        configuration_data.network_interface = 'noop'
        configuration_data.management_interface = 'redfish'
        configuration_data.boot_interface = 'redfish-virtual-media'
        configuration_data.power_interface = 'redfish'
        configuration_data.rescue_interface = 'no-rescue'
        configuration_data.raid_interface = 'redfish'
        configuration_data.inspect_interface = 'redfish'
        configuration_data.bios_interface = 'redfish'
        configuration_data.vendor_interface = 'redfish'
        configuration_data.console_interface = 'no-console'
        configuration_data.deploy_interface = 'ramdisk'
        configuration_data.storage_interface = 'noop'


        # TODO: this is totally made up configuration - we need to get actual
        # data from the nautbot. We may also need to query Ironic API for
        # specific port ids
        network_data = NetworkInfo(
            links=[
                PhysicalNic(
                    ethernet_mac_address="de:ad:de:ad:be:ef",
                    id=id_of_exnet_interface,
                ),
                PhysicalNic(
                    ethernet_mac_address="de:ad:de:ad:ca:fe",
                    id="3d488fe3-9777-4f7c-98c9-1e29111a55bf",
                ),
            ],
            networks=[
                Network(
                    id="abcd",
                    network_id="exnet0",
                    link=id_of_exnet_interface,
                    type="ipv4",
                    ip_address=exnet_ip,
                    netmask=exnet_netmask,
                ),
                Network(
                    id="defg",
                    network_id="servicenet0",
                    link="3d488fe3-9777-4f7c-98c9-1e29111a55bf",
                    type="ipv4",
                    ip_address="192.168.66.3",
                    netmask="255.255.255.0",
                    routes=[
                        NetworkRoute(
                            network="10.0.8.0",
                            netmask="255.255.255.252",
                            gateway="192.168.66.7",
                        )
                    ],
                ),
            ],
            services=[
                Service(type="dns", address="8.8.8.8"),
            ],
        )
        network_data_dict = asdict(network_data)
        self._validate_network_data(network_data_dict)
        # configuration_data.network_data = network_data_dict
        arguments = configuration_data.create_arguments()
        response = requests.post("http://192.168.1.177:12000/nautobot", 
                                 json=arguments,
                                 headers={"Content-Type": "application/json"})
        print(response)
        return response

        # nodes = client.list_nodes()
        # for node in nodes:
        #     logger.info(f"Found Node: {node.to_dict()}")

    def _validate_network_data(self, data):
        with (Path(__file__).parent / "ironic/network_data.schema.json").open(
            "r"
        ) as schema_file:
            schema = json.load(schema_file)
        return jsonschema.validate(data, schema)
