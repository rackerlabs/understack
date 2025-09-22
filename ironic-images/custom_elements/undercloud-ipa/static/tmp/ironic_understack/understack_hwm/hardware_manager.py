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
            [
                {
                    "address": "100.126.0.30/30",
                    "mac": "D4:04:E6:4F:87:85"
                },
                {
                    "address": "100.126.128.30/30",
                    "mac": "14:23:F3:F5:3B:A1"
                }
            ]
        """
        files = [
            {
                "path": "/config-2/somefile.txt",
                "partition": "/dev/sda4",
                "content": file_contents,
                "mode": 644,
            }
        ]
        inject_files(node, ports, files)
