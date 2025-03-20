import copy
import json
import random
import uuid

import pytest
from neutron.db.models.segment import NetworkSegment
from neutron.db.models_v2 import Network
from neutron.db.models_v2 import Port as PortModel
from neutron.db.models_v2 import Subnet
from neutron.objects.network import NetworkSegment as SegmentObj
from neutron.objects.ports import Port as PortObject
from neutron.objects.trunk import SubPort
from neutron.objects.trunk import Trunk
from neutron.plugins.ml2.driver_context import NetworkContext
from neutron.plugins.ml2.driver_context import PortContext
from neutron.plugins.ml2.driver_context import SubnetContext
from neutron.plugins.ml2.models import PortBinding
from neutron.services.trunk.models import SubPort as SubPortModel
from neutron.services.trunk.models import Trunk as TrunkModel
from neutron_lib.api.definitions import portbindings
from neutron_lib.callbacks.events import DBEventPayload

from neutron_understack.nautobot import Nautobot
from neutron_understack.neutron_understack_mech import UnderstackDriver
from neutron_understack.tests.helpers import Ml2PluginNoInit
from neutron_understack.tests.helpers import extend_network_dict
from neutron_understack.tests.helpers import extend_port_dict_with_trunk
from neutron_understack.trunk import UnderStackTrunkDriver
from neutron_understack.undersync import Undersync


@pytest.fixture
def ucvni_group_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def network_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def subnet_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def port_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def vlan_group_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def vlan_num() -> int:
    return random.randint(1, 4094)


@pytest.fixture
def network_segment_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def project_id() -> str:
    return uuid.uuid4().hex


@pytest.fixture
def network(project_id, network_id) -> Network:
    return Network(id=str(network_id), project_id=project_id, external=None)


@pytest.fixture
def patch_extend_subnet(mocker) -> None:
    """Ml2 Plugin extend subnet patch.

    This patch is needed as the Ml2Pugin's _make_subnet_dict method is calling
    _ml2_md_extend_subnet_dict static method,that would try to call the real db object
    and we don't have access to db.

    Autouse is here used so it's run every time, thus eliminating the need to request
    it on any tests that use subnet.
    """
    mocker.patch(
        "neutron_understack.tests.helpers.Ml2PluginNoInit._ml2_md_extend_subnet_dict"
    )


@pytest.fixture
def ml2_plugin(patch_extend_subnet) -> Ml2PluginNoInit:
    return Ml2PluginNoInit()


@pytest.fixture
def subport(port_id, vlan_num) -> SubPort:
    return SubPort(segmentation_type="vlan", segmentation_id=vlan_num, port_id=port_id)


@pytest.fixture
def network_dict(ml2_plugin, network, network_segment) -> dict:
    network_details = ml2_plugin._make_network_dict(network, process_extensions=False)
    extend_network_dict(network_details, network)
    ml2_plugin.extend_network_dict_with_segment(network_segment, network_details)
    return network_details


@pytest.fixture
def network_segment(network) -> NetworkSegment:
    return NetworkSegment(network_type="vxlan", network=network)


@pytest.fixture
def vlan_network_segment(request, network_segment_id, network_id) -> SegmentObj:
    req = getattr(request, "param", {})
    return SegmentObj(
        id=network_segment_id,
        network_type="vlan",
        network_id=network_id,
        physical_network=req.get("physical_network"),
        revision_number=1,
        segment_index=1,
        is_dynamic=False,
        name="puc-abc",
        segmentation_id=req.get("segmentation_id", 1800),
    )


@pytest.fixture
def network_context(ml2_plugin, network_dict, network_segment) -> NetworkContext:
    return NetworkContext(
        ml2_plugin,
        "plugin_context",
        network_dict,
        segments=[network_segment],
    )


@pytest.fixture
def subnet(request, subnet_id, network_id) -> Subnet:
    req = getattr(request, "param", {})
    return Subnet(
        id=subnet_id,
        network_id=network_id,
        cidr="1.0.0.0/24",
        external=req.get("external", False),
    )


@pytest.fixture
def subnet_dict(ml2_plugin, subnet) -> dict:
    return ml2_plugin.construct_subnet_dict(subnet)


@pytest.fixture
def subnet_context(ml2_plugin, subnet_dict) -> SubnetContext:
    return SubnetContext(
        ml2_plugin,
        "plugin_context",
        subnet_dict,
        None,
    )


@pytest.fixture
def binding_profile(request, port_id) -> str:
    req = getattr(request, "param", {})
    return json.dumps(
        {
            "local_link_information": [
                {
                    "port_id": req.get("port_id", str(port_id)),
                    "switch_id": "11:22:33:44:55:66",
                }
            ]
        }
    )


@pytest.fixture
def trunk_model(subport_model) -> TrunkModel:
    return TrunkModel(sub_ports=[subport_model])


@pytest.fixture
def subport_model(vlan_num) -> SubPortModel:
    return SubPortModel(segmentation_type="vlan", segmentation_id=vlan_num)


@pytest.fixture
def port_model() -> PortModel:
    return PortModel()


@pytest.fixture
def trunk(subport, port_id) -> Trunk:
    return Trunk(sub_ports=[subport], port_id=port_id)


@pytest.fixture
def port_binding(binding_profile, port_model) -> PortBinding:
    binding = PortBinding(
        profile=binding_profile,
        port=port_model,
        vif_type=portbindings.VIF_TYPE_OTHER,
        vnic_type=portbindings.VNIC_BAREMETAL,
    )
    return binding


@pytest.fixture
def port_object(port_binding) -> PortObject:
    port_obj = PortObject()
    port_obj.from_db_object(port_binding.port)
    return port_obj


@pytest.fixture
def port_dict(request, port_binding, trunk_model, ml2_plugin) -> dict:
    req = getattr(request, "param", {})
    port_binding.vif_type = req.get("vif_type", port_binding.vif_type)
    portdict = ml2_plugin.construct_port_dict(port_binding.port)
    if req.get("trunk"):
        trunk_model.port = port_binding.port
        return extend_port_dict_with_trunk(portdict, port_binding.port)
    return portdict


@pytest.fixture
def port_context(network_context, port_dict, port_binding, ml2_plugin) -> PortContext:
    return PortContext(
        ml2_plugin,
        "plugin_context",
        port_dict,
        network_context,
        port_binding,
        None,
        original_port=copy.deepcopy(port_dict),
    )


@pytest.fixture
def nautobot_client(mocker) -> Nautobot:
    return mocker.MagicMock(spec_set=Nautobot)


@pytest.fixture
def understack_driver(nautobot_client) -> UnderstackDriver:
    driver = UnderstackDriver()
    driver.nb = nautobot_client
    driver.undersync = Undersync("auth_token", "api_url")
    return driver


@pytest.fixture
def understack_trunk_driver(understack_driver) -> UnderStackTrunkDriver:
    return UnderStackTrunkDriver.create(understack_driver)


@pytest.fixture(autouse=True)
def undersync_sync_devices_patch(mocker, understack_driver) -> None:
    mocker.patch.object(understack_driver.undersync, "sync_devices")


@pytest.fixture
def update_nautobot_patch(mocker, understack_driver) -> None:
    mocker.patch.object(understack_driver, "update_nautobot")


@pytest.fixture
def utils_fetch_subport_network_id_patch(mocker, network_id) -> None:
    mocker.patch(
        "neutron_understack.utils.fetch_subport_network_id",
        return_value=str(network_id),
    )


@pytest.fixture
def trunk_payload_metadata(subport) -> dict:
    return {"subports": [subport]}


@pytest.fixture
def trunk_payload(trunk_payload_metadata, trunk) -> DBEventPayload:
    return DBEventPayload("context", metadata=trunk_payload_metadata, states=[trunk])


@pytest.fixture
def ml2_understack_conf(mocker, ucvni_group_id) -> None:
    mocker.patch(
        "neutron_understack.neutron_understack_mech.cfg.CONF.ml2_understack.ucvni_group",
        str(ucvni_group_id),
    )
    mocker.patch(
        "neutron_understack.neutron_understack_mech.cfg.CONF.ml2_understack.network_node_switchport_uuid",
        "a27f7260-a7c5-4f0c-ac70-6258b026d368",
    )
    mocker.patch(
        "neutron_understack.neutron_understack_mech.cfg.CONF.ml2_understack.undersync_dry_run",
        False,
    )


@pytest.fixture
def ucvni_create_response(ucvni_group_id) -> list[dict]:
    return [
        {
            "id": "63a2da8b-9da5-493a-b5ac-2ae62f663e1a",
            "name": "PROV-NET500",
            "ucvni_id": 200054,
            "ucvni_type": "TENANT",
            "ucvni_group": {
                "id": str(ucvni_group_id),
            },
            "tenant": {
                "id": "d3c2c85b-dbf2-4ff5-843f-323524b63768",
            },
            "status": {
                "id": "d4bcbafa-3033-433b-b21b-a20acf9d1324",
            },
        }
    ]
