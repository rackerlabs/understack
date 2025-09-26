import base64

from ironic_python_agent import hardware
from ironic_python_agent.inject_files import inject_files
from oslo_log import log

LOG = log.getLogger()


class UnderstackHardwareManager(hardware.HardwareManager):
    """Hardware Manager that injects Undercloud specific metadata."""

    HARDWARE_MANAGER_NAME = "UnderstackHardwareManager"
    HARDWARE_MANAGER_VERSION = "1"

    def evaluate_hardware_support(self):
        """Declare level of hardware support provided.

        Since this example is explicitly about enforcing business logic during
        cleaning, we want to return a static value.

        :returns: HardwareSupport level for this manager.
        """
        return hardware.HardwareSupport.SERVICE_PROVIDER

    def get_deploy_steps(self, node, ports):
        return [
            {
                "step": "write_storage_ips",
                "priority": 50,
                "interface": "deploy",
                "reboot_requested": False,
            }
        ]

    def get_service_steps(self, node, ports):
        return [
            {
                "step": "write_storage_ips",
                "priority": 50,
                "interface": "deploy",
                "reboot_requested": False,
            }
        ]

        # "Files to inject, a list of file structures with keys: 'path' "
        # "(path to the file), 'partition' (partition specifier), "
        # "'content' (base64 encoded string), 'mode' (new file mode) and "
        # "'dirmode' (mode for the leaf directory, if created). "
        # "Merged with the values from node.properties[inject_files]."

    def write_storage_ips(self, node, ports):
        # If not specified, the agent will determine the partition based on the
        # first part of the path.
        # partition = None
        file_contents = """
datasource:
  NoCloud:
    network-config: |
    version: 2
    ethernets:
      interface0:
        match:
          macaddress: "52:54:00:12:34:00"
        set-name: interface0
        addresses:
          - 100.126.0.6/255.255.255.252
        gateway4: 100.126.0.5
      interface1:
        match:
          macaddress: "14:23:F3:F5:3A:D1"
        set-name: interface0
        addresses:
          - 100.126.128.6/255.255.255.252
        gateway4: 100.126.128.5
"""
        file_encoded = base64.b64encode(file_contents.encode("utf-8")).decode("utf-8")
        files = [
            {
                "path": "/etc/cloud/cloud.cfg.d/95-undercloud-storage.cfg",
                "partition": "/dev/sda3",
                "content": file_encoded,
                "mode": 644,
            }
        ]
        inject_files(node, ports, files)
