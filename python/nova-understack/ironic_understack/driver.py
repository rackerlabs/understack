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
        logger.debug("original_network_info: %s", original)

        # original  looks like:
        # [
        #     {
        #         "id": "88bd37f8-f319-4c86-b1c1-755b0d1d422e",
        #         "address": "fa:16:3e:e3:89:c0",
        #         "network": {
        #             "id": "81d7333e-ebef-4522-80ed-5256fb5102ed",
        #             "bridge": null,
        #             "label": "marek-ipa-test",
        #             "subnets": [],
        #             "meta": {
        #                 "injected": false,
        #                 "tenant_id": "dcd8e230ebf448df85cd03d332e12ac1",
        #                 "mtu": 9000,
        #                 "physical_network": null,
        #                 "tunneled": true,
        #             },
        #         },
        #         "type": "unbound",
        #         "details": {},
        #         "devname": "tap88bd37f8-f3",
        #         "ovs_interfaceid": null,
        #         "qbh_params": null,
        #         "qbg_params": null,
        #         "active": false,
        #         "vnic_type": "normal",
        #         "profile": {},
        #         "preserve_on_delete": false,
        #         "delegate_create": true,
        #         "trunk_vifs": [],
        #         "meta": {},
        #     }
        # ]

        # merged = copy.deepcopy(original)
        # merged["networks"].append(
        #     model.VIF(
        #         type=model.VIF_TYPE_OTHER,
        #         active=True,
        #         vnic_type=model.VNIC_TYPE_BAREMETAL,
        #         network=model.Network(
        #             id=str(uuid.UUID()),
        #             subnets=model.Subnet(
        #                 cidr="126.0.0.0/30",
        #                 version=4,
        #                 routes=model.Route(
        #                     cidr="127.0.0.0/16", gateway=model.IP(address="126.0.0.1")
        #                 ),
        #             ),
        #         ),
        #     )
        # )
        # for link in new_info["links"]:
        #     merged["links"].append(link)
        #
        # for network in new_info["networks"]:
        #     merged["networks"].append(network)
        return original
