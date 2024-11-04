import json
import logging
from pprint import pprint
from uuid import UUID

import neutron_lib.api.definitions.portbindings as portbindings
from neutron_lib import constants as p_const
from neutron_lib import exceptions as exc
from neutron_lib.plugins.ml2 import api
from neutron_lib.plugins.ml2.api import (
    MechanismDriver,
    NetworkContext,
    PortContext,
    SubnetContext,
)
from oslo_config import cfg

from neutron_understack import config
from neutron_understack.argo.workflows import ArgoClient
from neutron_understack.nautobot import Nautobot

LOG = logging.getLogger(__name__)


config.register_ml2_type_understack_opts(cfg.CONF)
config.register_ml2_understack_opts(cfg.CONF)


def dump_context(
    context: NetworkContext | SubnetContext | PortContext,
) -> dict:
    # RESOURCE_ATTRIBUTE_MAP
    # from neutron_lib.api.definitions import network, subnet, port, portbindings
    # The properties of a NetworkContext.current are defined in
    #   network.RESOURCE_ATTRIBUTE_MAP
    # The properties of a SubnetContext.current are defined in
    #   subnet.RESOURCE_ATTRIBUTE_MAP
    # The properties of a PortContext.current are defined in
    #   port.RESOURCE_ATTRIBUTE_MAP
    attr_map = {
        NetworkContext: ("current", "original", "network_segments"),
        SubnetContext: ("current", "original"),
        PortContext: (
            "current",
            "original",
            "status",
            "original_status",
            "network",
            "binding_levels",
            "original_binding_levels",
            "top_bound_segment",
            "original_top_bound_segment",
            "bottom_bound_segment",
            "original_bottom_bound_segment",
            "host",
            "original_host",
            "vif_type",
            "original_vif_type",
            "vif_details",
            "original_vif_details",
            "segments_to_bind",
        ),
    }
    retval = {"errors": [], "other_attrs": []}
    if isinstance(context, NetworkContext):
        attrs_to_dump = attr_map[NetworkContext]
    elif isinstance(context, SubnetContext):
        attrs_to_dump = attr_map[SubnetContext]
    elif isinstance(context, PortContext):
        attrs_to_dump = attr_map[PortContext]
    else:
        retval["errors"].append(f"Error: unknown object type {type(context)}")
        return retval

    attrs = vars(context)
    for attr in attrs:
        if attr in attrs_to_dump:
            try:
                val = getattr(context, attr)
                retval.update({attr: val})
            except Exception as e:
                retval["errors"].append(f"Error dumping {attr}: {str(e)}")
        else:
            retval["other_attrs"].append(attr)
    return retval


def log_call(
    method: str, context: NetworkContext | SubnetContext | PortContext
) -> None:
    data = dump_context(context)
    data.update({"method": method})
    try:
        jsondata = json.dumps(data)
    except Exception as e:
        LOG.error(
            "failed to dump %s object to JSON on %s call: %s",
            str(context),
            method,
            str(e),
        )
        return
    LOG.info("%s method called with data: %s", method, jsondata)
    LOG.debug("%s method executed with context:", method)
    pprint(context.current)


class UnderstackDriver(MechanismDriver):
    # See MechanismDriver docs for resource_provider_uuid5_namespace
    resource_provider_uuid5_namespace = UUID("6eae3046-4072-11ef-9bcf-d6be6370a162")

    def initialize(self):
        conf = cfg.CONF.ml2_understack
        self.nb = Nautobot(conf.nb_url, conf.nb_token)

    def create_network_precommit(self, context):
        log_call("create_network_precommit", context)

    def create_network_postcommit(self, context):
        log_call("create_network_postcommit", context)

        network = context.current
        network_id = network["id"]
        network_name = network["name"]
        provider_type = network.get("provider:network_type")
        segmentation_id = network.get("provider:segmentation_id")
        physnet = network.get("provider:physical_network")

        if provider_type == p_const.TYPE_VXLAN:
            conf = cfg.CONF.ml2_understack
            ucvni_group = conf.ucvni_group
            try:
                self.nb.ucvni_create(
                    network_id, ucvni_group, network_name, segmentation_id
                )
            except Exception as e:
                LOG.exception(
                    "unable to create network %(net_id)s", {"net_id": network_id}
                )
                raise exc.NetworkNotFound(net_id=network_id) from e

            LOG.info(
                "network %(net_id)s has been added on ucvni_group %(ucvni_group), "
                "physnet %(physnet)",
                {"net_id": network_id, "ucvni_group": ucvni_group, "physnet": physnet},
            )

    def update_network_precommit(self, context):
        log_call("update_network_precommit", context)

    def update_network_postcommit(self, context):
        log_call("update_network_postcommit", context)

    def delete_network_precommit(self, context):
        log_call("delete_network_precommit", context)

    def delete_network_postcommit(self, context):
        log_call("delete_network_postcommit", context)

    def create_subnet_precommit(self, context):
        log_call("create_subnet_precommit", context)

    def create_subnet_postcommit(self, context):
        log_call("create_subnet_postcommit", context)

    def update_subnet_precommit(self, context):
        log_call("update_subnet_precommit", context)

    def update_subnet_postcommit(self, context):
        log_call("update_subnet_postcommit", context)

    def delete_subnet_precommit(self, context):
        log_call("delete_subnet_precommit", context)

    def delete_subnet_postcommit(self, context):
        log_call("delete_subnet_postcommit", context)

    def create_port_precommit(self, context):
        log_call("create_port_precommit", context)

    def create_port_postcommit(self, context):
        log_call("create_port_postcommit", context)

    def update_port_precommit(self, context):
        log_call("update_port_precommit", context)

    def update_port_postcommit(self, context):
        log_call("update_port_postcommit", context)

        argo_client = ArgoClient(
            logger=LOG,
            api_url=cfg.CONF.ml2_type_understack.argo_api_url,
            namespace=cfg.CONF.ml2_type_understack.argo_namespace,
        )

        self._move_to_network(
            vif_type=context.current["binding:vif_type"],
            mac_address=context.current["mac_address"],
            device_uuid=context.current["binding:host_id"],
            network_id=context.current["network_id"],
            argo_client=argo_client,
        )

    def delete_port_precommit(self, context):
        log_call("delete_port_precommit", context)

    def delete_port_postcommit(self, context):
        log_call("delete_port_postcommit", context)

    def bind_port(self, context):
        log_call("bind_port", context)
        for segment in context.network.network_segments:
            if self.check_segment(segment):
                context.set_binding(
                    segment[api.ID],
                    portbindings.VIF_TYPE_OTHER,
                    {},
                    status=p_const.PORT_STATUS_ACTIVE,
                )
                LOG.debug(f"Bound segment: {segment}")
                return
            else:
                LOG.debug(
                    "Refusing to bind port for segment ID %(id)s, "
                    "segment %(seg)s, phys net %(physnet)s, and "
                    "network type %(nettype)s",
                    {
                        "id": segment[api.ID],
                        "seg": segment[api.SEGMENTATION_ID],
                        "physnet": segment[api.PHYSICAL_NETWORK],
                        "nettype": segment[api.NETWORK_TYPE],
                    },
                )

    def check_segment(self, segment):
        """Verify a segment is valid for the Understack MechanismDriver.

        Verify the requested segment is supported by Understack and return True or
        False to indicate this to callers.
        """
        network_type = segment[api.NETWORK_TYPE]
        return network_type in [
            p_const.TYPE_LOCAL,
            p_const.TYPE_GRE,
            p_const.TYPE_VXLAN,
            p_const.TYPE_VLAN,
            p_const.TYPE_FLAT,
        ]

    def check_vlan_transparency(self, context):
        log_call("check_vlan_transparency", context)

    def _move_to_network(
        self,
        vif_type: str,
        mac_address: str,
        device_uuid: UUID,
        network_id: str,
        argo_client: ArgoClient,
    ):
        """Triggers Argo "trigger-undersync" workflow.

        This has the effect of connecting our server to the given networks: either
        "provisioning" (for PXE booting) or "tenant" (normal access to customer's
        networks).  The choice of network is based on the network ID.

        This only happens when vif_type is VIF_TYPE_OTHER.

        argo_client is injected by the caller to make testing easier
        """
        if vif_type != portbindings.VIF_TYPE_OTHER:
            return

        if network_id == cfg.CONF.ml2_type_understack.provisioning_network:
            network_name = "provisioning"
        else:
            network_name = "tenant"

        LOG.debug(f"Selected {network_name=} for {device_uuid=} {mac_address=}")

        result = argo_client.submit(
            template_name="undersync-device",
            entrypoint="trigger-undersync",
            parameters={
                "interface_mac": mac_address,
                "device_uuid": device_uuid,
                "network_name": network_name,
                "network_id": network_id,
                "dry_run": cfg.CONF.ml2_type_understack.argo_dry_run,
                "force": cfg.CONF.ml2_type_understack.argo_force,
            },
            service_account=cfg.CONF.ml2_type_understack.argo_workflow_sa,
        )
        LOG.info(f"Binding workflow submitted: {result}")
