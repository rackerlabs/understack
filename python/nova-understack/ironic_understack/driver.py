from nova import exception
from nova.i18n import _
from nova.virt.ironic.driver import IronicDriver


class IronicUnderstackDriver(IronicDriver):
    capabilities = IronicDriver.capabilities
    rebalances_nodes = IronicDriver.rebalances_nodes

    def spawn(
        self,
        context,
        instance,
        image_meta,
        injected_files,
        admin_password,
        allocations,
        network_info=None,
        block_device_info=None,
        power_on=True,
        accel_info=None,
    ):
        """Deploy an instance.

        Args:
            context: The security context.
            instance: The instance object.
            image_meta: Image dict returned by nova.image.glance
                that defines the image from which to boot this instance.
            injected_files: User files to inject into instance.
            admin_password: Administrator password to set in instance.
            allocations: Information about resources allocated to the
                instance via placement, of the form returned by
                SchedulerReportClient.get_allocations_for_consumer.
                Ignored by this driver.
            network_info: Instance network information.
            block_device_info: Instance block device information.
            accel_info: Accelerator requests for this instance.
            power_on: True if the instance should be powered on, False otherwise.
        """
        node_id = instance.get("node")
        if not node_id:
            raise exception.NovaException(
                _("Ironic node uuid not supplied to driver for instance %s.")
                % instance.uuid
            )

        storage_netinfo = self._lookup_storage_netinfo(node_id)
        network_info = self._merge_storage_netinfo(network_info, storage_netinfo)

        return super().spawn(
            context,
            instance,
            image_meta,
            injected_files,
            admin_password,
            allocations,
            network_info,
            block_device_info,
            power_on,
            accel_info,
        )

    def _lookup_storage_netinfo(self, node_id):
        return {
            "links": [
                {
                    "id": "storage-iface-uuid",
                    "vif_id": "generate_or_obtain",
                    "type": "phy",
                    "mtu": 9000,
                    "ethernet_mac_address": "d4:04:e6:4f:90:18",
                }
            ],
            "networks": [
                {
                    "id": "network0",
                    "type": "ipv4",
                    "link": "storage-iface-uuid",
                    "ip_address": "126.0.0.2",
                    "netmask": "255.255.255.252",
                    "routes": [
                        {
                            "network": "127.0.0.0",
                            "netmask": "255.255.0.0",
                            "gateway": "126.0.0.1",
                        }
                    ],
                    "network_id": "generate_or_obtain",
                }
            ],
        }

    def _merge_storage_netinfo(self, original, new_info):
        print("original network_info: %s", original)
        return original
