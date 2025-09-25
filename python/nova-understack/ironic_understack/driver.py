import logging

from nova.virt.ironic.driver import IronicDriver

logger = logging.getLogger(__name__)


class IronicUnderstackDriver(IronicDriver):
    capabilities = IronicDriver.capabilities
    rebalances_nodes = IronicDriver.rebalances_nodes

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

    def _get_network_metadata(self, node, network_info):
        base_metadata = super()._get_network_metadata(node, network_info)
        if not base_metadata:
            return base_metadata
        additions = self._lookup_storage_netinfo(node["uuid"])
        for link in additions["links"]:
            base_metadata["links"].append(link)
        for network in additions["networks"]:
            base_metadata["networks"].append(network)
        return base_metadata

    def _merge_storage_netinfo(self, original, new_info):
        print("original network_info: %s", original)

        return original
