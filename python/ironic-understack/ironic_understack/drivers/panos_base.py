"""What every PAN-OS (Palo Alto) interface shares."""

from ironic.common import exception


class PanosInterface:
    """Mixin for PAN-OS interfaces: each reaches the appliance at management_ip."""

    def get_properties(self):
        return {
            "management_ip": "Address of the appliance's management interface, "
            "used for the XML API. Required.",
        }

    def validate(self, task):
        if not task.node.driver_info.get("management_ip"):
            raise exception.MissingParameterValue(
                f"Node {task.node.uuid} is missing driver_info management_ip"
            )
