import copy
import json
import uuid

import pytest
from neutron.db.models.segment import NetworkSegment
from neutron.db.models_v2 import Network
from neutron.db.models_v2 import Port
from neutron.db.models_v2 import Subnet
from neutron.plugins.ml2.driver_context import NetworkContext
from neutron.plugins.ml2.driver_context import PortContext
from neutron.plugins.ml2.driver_context import SubnetContext
from neutron.plugins.ml2.models import PortBinding
from neutron.services.trunk.models import SubPort
from neutron.services.trunk.models import Trunk
from neutron_lib.api.definitions import portbindings

from neutron_understack.nautobot import Nautobot
from neutron_understack.neutron_understack_mech import UnderstackDriver
from neutron_understack.tests.helpers import Ml2PluginNoInit
from neutron_understack.tests.helpers import extend_port_dict_with_trunk
from neutron_understack.undersync import Undersync


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
def subport() -> SubPort:
    return SubPort(segmentation_type="vlan", segmentation_id=333)


@pytest.fixture
def network_dict(ml2_plugin) -> dict:
    return ml2_plugin._make_network_dict(Network(), process_extensions=False)


@pytest.fixture
def network_segment() -> NetworkSegment:
    return NetworkSegment(network_type="vxlan")


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
def trunk(subport) -> Trunk:
    return Trunk(sub_ports=[subport])


@pytest.fixture
def port_binding(binding_profile) -> PortBinding:
    binding = PortBinding(
        profile=binding_profile,
        port=Port(),
        vif_type=portbindings.VIF_TYPE_OTHER,
        vnic_type=portbindings.VNIC_BAREMETAL,
    )
    return binding


@pytest.fixture
def port_dict(request, port_binding, trunk, ml2_plugin) -> dict:
    req = getattr(request, "param", {})
    port_binding.vif_type = req.get("vif_type", port_binding.vif_type)
    portdict = ml2_plugin.construct_port_dict(port_binding.port)
    if req.get("trunk"):
        trunk.port = port_binding.port
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


@pytest.fixture(autouse=True)
def undersync_sync_devices_patch(mocker, understack_driver) -> None:
    mocker.patch.object(understack_driver.undersync, "sync_devices")


@pytest.fixture
def update_nautobot_patch(mocker, understack_driver) -> None:
    mocker.patch.object(understack_driver, "update_nautobot")
