import logging
from types import SimpleNamespace

import pytest
from neutron_lib import exceptions as n_exc

from neutron_understack.l3_router import palo_alto_wiring

_ANNOTATED_PARENT = {
    "id": "parent-1",
    "binding:host_id": "node-1",
    "binding:profile": {
        "physical_network": "n11-22-network",
        "local_link_information": [{"switch_id": "aa", "port_id": "Eth1/1"}],
    },
}

# e.g. the enrolled baremetal port had no physical_network
_UNANNOTATED_PARENT = {"id": "parent-1", "binding:host_id": "", "binding:profile": {}}

_GATEWAY_PORT = {
    "id": "gw-1",
    "device_id": "r1",
    "device_owner": "network:router_gateway",
}

_INTERFACE_PORT = {
    "id": "intf-1",
    "device_id": "r1",
    "device_owner": "network:router_interface",
}

# A trunk whose gateway and first interface already use VLANs 200 and 201.
_TRUNK_USING_200_AND_201 = {
    "id": "trunk-1",
    "sub_ports": [
        {"port_id": "gw-1", "segmentation_type": "vlan", "segmentation_id": 200},
        {"port_id": "intf-1", "segmentation_type": "vlan", "segmentation_id": 201},
    ],
}


@pytest.fixture
def core_plugin(mocker):
    core = mocker.Mock()
    core.get_networks.return_value = [{"id": "anchor-net"}]  # anchor exists
    mocker.patch.object(palo_alto_wiring.directory, "get_plugin", return_value=core)
    return core


@pytest.fixture
def trunk_plugin(mocker):
    trunk_plugin = mocker.Mock()
    mocker.patch.object(
        palo_alto_wiring.utils, "fetch_trunk_plugin", return_value=trunk_plugin
    )
    return trunk_plugin


@pytest.fixture
def ironic(mocker):
    return mocker.Mock()


@pytest.fixture
def node(mocker, ironic):
    """The Ironic node adopted for router r1."""
    node = mocker.Mock(id="node-1")
    ironic.node_by_instance_uuid.return_value = node
    return node


@pytest.fixture
def device_id(mocker):
    """The DB helpers that clear and restore a port's device_id around a subport add."""
    return SimpleNamespace(
        clear=mocker.patch.object(palo_alto_wiring.utils, "clear_device_id_for_port"),
        restore=mocker.patch.object(
            palo_alto_wiring.utils, "set_device_id_and_owner_for_port"
        ),
    )


@pytest.fixture
def wiring(mocker, ironic, core_plugin, trunk_plugin):
    # get_admin_context() would init oslo policy; not needed for these tests.
    mocker.patch.object(palo_alto_wiring.n_context, "get_admin_context")
    return palo_alto_wiring.PaloAltoWiring(ironic=lambda: ironic)


class TestExceptionHttpCodes:
    """Exceptions must map to real HTTP codes, not 500.

    neutron's FAULT_MAP maps Conflict->409 and BadRequest->400; the base
    NeutronException falls through to 500.
    """

    def test_no_subport_vlan_available_is_conflict(self):
        assert issubclass(
            palo_alto_wiring.NoPaloAltoSubportVlanAvailable, n_exc.Conflict
        )

    @pytest.mark.parametrize(
        "exc",
        [
            palo_alto_wiring.PaloAltoNodeNotAdopted,
            palo_alto_wiring.PaloAltoParentNotAnnotated,
        ],
    )
    def test_wiring_errors_are_bad_request(self, exc):
        assert issubclass(exc, n_exc.BadRequest)


class TestNames:
    def test_names_are_deterministic(self):
        assert palo_alto_wiring._parent_port_name("r1") == "palo-alto-router-anchor-r1"
        assert palo_alto_wiring._trunk_name("r1") == "palo-alto-router-trunk-r1"


class TestFirstFreeVlan:
    def test_starts_at_requested_vlan(self):
        assert palo_alto_wiring._first_free_vlan([(1, 300)], set(), 201) == 201

    def test_skips_used_vlans(self):
        assert palo_alto_wiring._first_free_vlan([(200, 205)], {201, 202}, 201) == 203

    def test_continues_into_next_range(self):
        assert (
            palo_alto_wiring._first_free_vlan([(200, 201), (300, 301)], {201}, 201)
            == 300
        )

    def test_accepts_unsorted_ranges(self):
        assert (
            palo_alto_wiring._first_free_vlan([(300, 301), (200, 210)], set(), 201)
            == 201
        )

    def test_returns_none_when_exhausted(self):
        assert palo_alto_wiring._first_free_vlan([(200, 201)], {200, 201}, 200) is None


class TestSubportHelpers:
    def test_has_subport(self):
        trunk = {"id": "trunk-1", "sub_ports": [{"port_id": "gw-1"}]}

        assert palo_alto_wiring._has_subport(trunk, "gw-1") is True
        assert palo_alto_wiring._has_subport(trunk, "intf-1") is False
        assert palo_alto_wiring._has_subport({"id": "trunk-1"}, "gw-1") is False

    def test_used_subport_vlans_counts_only_vlan_tags(self):
        trunk = {
            "id": "trunk-1",
            "sub_ports": [
                {"port_id": "a", "segmentation_type": "vlan", "segmentation_id": 200},
                {"port_id": "b", "segmentation_type": "vlan", "segmentation_id": None},
                {"port_id": "c", "segmentation_type": "inherit"},
            ],
        }

        assert palo_alto_wiring._used_subport_vlans(trunk) == {200}


class TestMissingBindingFields:
    def test_none_missing_when_annotated(self):
        assert palo_alto_wiring._missing_binding_fields(_ANNOTATED_PARENT) == []

    def test_all_missing_when_unbound(self):
        port = {"id": "parent-1", "binding:host_id": "", "binding:profile": None}

        assert palo_alto_wiring._missing_binding_fields(port) == [
            "binding:host_id",
            "physical_network",
            "local_link_information",
        ]

    def test_reports_only_missing_profile_field(self):
        port = {
            **_ANNOTATED_PARENT,
            "binding:profile": {"local_link_information": [{"port_id": "Eth1/1"}]},
        }

        assert palo_alto_wiring._missing_binding_fields(port) == ["physical_network"]


class TestLookups:
    def test_trunk_plugin_delegates_to_utils(self, wiring, trunk_plugin):
        assert wiring._trunk_plugin() is trunk_plugin

    def test_gateway_port_found_filters_by_owner_and_router(self, wiring, core_plugin):
        core_plugin.get_ports.return_value = [{"id": "gw-1"}]

        assert wiring.gateway_port_for_router("r1") == {"id": "gw-1"}
        _args, kwargs = core_plugin.get_ports.call_args
        assert kwargs["filters"]["device_id"] == ["r1"]
        assert kwargs["filters"]["device_owner"] == ["network:router_gateway"]

    def test_gateway_port_none_when_absent(self, wiring, core_plugin):
        core_plugin.get_ports.return_value = []

        assert wiring.gateway_port_for_router("r1") is None


class TestParentPort:
    def test_creates_parent_when_absent(self, wiring, core_plugin):
        core_plugin.get_ports.return_value = []
        core_plugin.create_port.return_value = {"id": "parent-new"}

        port = wiring._ensure_parent_port("r1")

        assert port == {"id": "parent-new"}
        core_plugin.create_port.assert_called_once()
        _ctx, body = core_plugin.create_port.call_args[0]
        net = body["port"]
        assert net["name"] == "palo-alto-router-anchor-r1"
        assert net["network_id"] == "anchor-net"
        assert net["binding:vnic_type"] == "baremetal"
        assert net["device_id"] == "r1"

    def test_reuses_existing_parent(self, wiring, core_plugin):
        core_plugin.get_ports.return_value = [{"id": "parent-existing"}]

        port = wiring._ensure_parent_port("r1")

        assert port == {"id": "parent-existing"}
        core_plugin.create_port.assert_not_called()


class TestParentVifAttach:
    @pytest.fixture(autouse=True)
    def _not_attached_yet(self, ironic, core_plugin):
        ironic.node_vif_ids.return_value = []
        core_plugin.get_port.return_value = _ANNOTATED_PARENT

    def test_attaches_when_not_already(self, wiring, ironic, node):
        result = wiring._ensure_parent_vif_attached("r1", {"id": "parent-1"})

        ironic.attach_vif_to_node.assert_called_once_with(node, "parent-1")
        assert result == _ANNOTATED_PARENT  # fresh, annotated copy returned

    def test_recovers_when_attach_raises_after_vif_lands(self, wiring, ironic, node):
        ironic.node_vif_ids.side_effect = [[], ["parent-1"]]
        ironic.attach_vif_to_node.side_effect = RuntimeError("rpc timeout")

        result = wiring._ensure_parent_vif_attached("r1", {"id": "parent-1"})

        ironic.attach_vif_to_node.assert_called_once_with(node, "parent-1")
        assert result == _ANNOTATED_PARENT

    def test_reraises_attach_error_when_vif_did_not_land(self, wiring, ironic, node):
        ironic.node_vif_ids.side_effect = [[], []]
        ironic.attach_vif_to_node.side_effect = RuntimeError("rpc timeout")

        with pytest.raises(RuntimeError, match="rpc timeout"):
            wiring._ensure_parent_vif_attached("r1", {"id": "parent-1"})

    def test_skips_attach_when_already_attached(self, wiring, ironic, node):
        ironic.node_vif_ids.return_value = ["parent-1"]

        wiring._ensure_parent_vif_attached("r1", {"id": "parent-1"})

        ironic.attach_vif_to_node.assert_not_called()

    def test_raises_when_no_adopted_node(self, wiring, ironic):
        ironic.node_by_instance_uuid.return_value = None

        with pytest.raises(palo_alto_wiring.PaloAltoNodeNotAdopted, match="router r1 "):
            wiring._ensure_parent_vif_attached("r1", {"id": "parent-1"})
        ironic.attach_vif_to_node.assert_not_called()

    def test_raises_when_parent_not_annotated(self, wiring, core_plugin, node):
        core_plugin.get_port.return_value = _UNANNOTATED_PARENT

        with pytest.raises(
            palo_alto_wiring.PaloAltoParentNotAnnotated,
            match=r"parent port parent-1 .*\(missing binding:host_id, physical_network",
        ):
            wiring._ensure_parent_vif_attached("r1", {"id": "parent-1"})

    def test_recovery_logs_original_attach_error(self, wiring, ironic, node, caplog):
        ironic.node_vif_ids.side_effect = [[], ["parent-1"]]
        error = RuntimeError("rpc timeout")
        ironic.attach_vif_to_node.side_effect = error

        with caplog.at_level(logging.WARNING, logger=palo_alto_wiring.__name__):
            wiring._ensure_parent_vif_attached("r1", {"id": "parent-1"})

        [record] = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert "raised, but the VIF is attached" in record.getMessage()
        assert record.exc_info[1] is error

    def test_recovery_raises_when_landed_vif_is_not_annotated(
        self, wiring, ironic, core_plugin, node
    ):
        core_plugin.get_port.return_value = _UNANNOTATED_PARENT
        ironic.node_vif_ids.side_effect = [[], ["parent-1"]]
        ironic.attach_vif_to_node.side_effect = RuntimeError("rpc timeout")

        with pytest.raises(palo_alto_wiring.PaloAltoParentNotAnnotated):
            wiring._ensure_parent_vif_attached("r1", {"id": "parent-1"})

    def test_reraises_attach_error_when_recheck_fails(self, wiring, ironic, node):
        ironic.node_vif_ids.side_effect = [[], RuntimeError("ironic unavailable")]
        ironic.attach_vif_to_node.side_effect = RuntimeError("rpc timeout")

        with pytest.raises(RuntimeError, match="rpc timeout"):
            wiring._ensure_parent_vif_attached("r1", {"id": "parent-1"})

    def test_raises_when_already_attached_parent_is_not_annotated(
        self, wiring, ironic, core_plugin, node
    ):
        ironic.node_vif_ids.return_value = ["parent-1"]
        core_plugin.get_port.return_value = _UNANNOTATED_PARENT

        with pytest.raises(palo_alto_wiring.PaloAltoParentNotAnnotated):
            wiring._ensure_parent_vif_attached("r1", {"id": "parent-1"})
        ironic.attach_vif_to_node.assert_not_called()


class TestTrunk:
    def test_creates_trunk_when_absent(self, wiring, trunk_plugin):
        trunk_plugin.get_trunks.return_value = []
        trunk_plugin.create_trunk.return_value = {"id": "trunk-new"}

        trunk = wiring._ensure_trunk("r1", {"id": "parent-1"})

        assert trunk == {"id": "trunk-new"}
        trunk_plugin.create_trunk.assert_called_once()
        _ctx, body = trunk_plugin.create_trunk.call_args[0]
        assert body["trunk"]["name"] == "palo-alto-router-trunk-r1"
        assert body["trunk"]["port_id"] == "parent-1"
        assert body["trunk"]["sub_ports"] == []

    def test_reuses_existing_trunk(self, wiring, trunk_plugin):
        trunk_plugin.get_trunks.return_value = [{"id": "trunk-existing"}]

        trunk = wiring._ensure_trunk("r1", {"id": "parent-1"})

        assert trunk == {"id": "trunk-existing"}
        trunk_plugin.create_trunk.assert_not_called()


class TestEnsureStack:
    def test_binds_parent_before_building_trunk(self, mocker, wiring):
        parent = {"id": "parent-1"}
        bound = {"id": "parent-1", "bound": True}
        trunk = {"id": "trunk-1"}
        m_parent = mocker.patch.object(
            wiring, "_ensure_parent_port", return_value=parent
        )
        m_vif = mocker.patch.object(
            wiring, "_ensure_parent_vif_attached", return_value=bound
        )
        m_trunk = mocker.patch.object(wiring, "_ensure_trunk", return_value=trunk)

        stack = wiring.ensure_stack("r1")

        m_parent.assert_called_once_with("r1")
        # VIF-attach runs on the parent BEFORE the trunk/subport
        m_vif.assert_called_once_with("r1", parent)
        # trunk + subport use the BOUND parent
        m_trunk.assert_called_once_with("r1", bound)
        assert stack == palo_alto_wiring.AttachmentStack(parent=bound, trunk=trunk)


class TestGatewaySubport:
    def test_adds_subport_with_fixed_vlan(self, wiring, trunk_plugin, device_id):
        trunk = {"id": "trunk-1", "sub_ports": []}

        wiring.add_gateway_subport("r1", trunk, dict(_GATEWAY_PORT))

        trunk_plugin.add_subports.assert_called_once()
        _ctx, trunk_id, body = trunk_plugin.add_subports.call_args[0]
        assert trunk_id == "trunk-1"
        sub = body["sub_ports"][0]
        assert sub["port_id"] == "gw-1"
        assert sub["segmentation_type"] == "vlan"
        assert sub["segmentation_id"] == palo_alto_wiring.GATEWAY_SUBPORT_VLAN
        # device_id cleared for the add (trunk validator rejects it) and restored
        device_id.clear.assert_called_once_with("gw-1")
        device_id.restore.assert_called_once_with(
            "gw-1", "r1", "network:router_gateway"
        )

    def test_add_subport_is_idempotent(self, wiring, trunk_plugin, device_id):
        trunk = {
            "id": "trunk-1",
            "sub_ports": [
                {
                    "port_id": "gw-1",
                    "segmentation_id": palo_alto_wiring.GATEWAY_SUBPORT_VLAN,
                }
            ],
        }

        wiring.add_gateway_subport("r1", trunk, dict(_GATEWAY_PORT))

        trunk_plugin.add_subports.assert_not_called()
        device_id.clear.assert_not_called()

    def test_restores_device_id_when_add_fails(self, wiring, trunk_plugin, device_id):
        trunk_plugin.add_subports.side_effect = RuntimeError("trunk rejected")
        trunk = {"id": "trunk-1", "sub_ports": []}

        with pytest.raises(RuntimeError, match="trunk rejected"):
            wiring.add_gateway_subport("r1", trunk, dict(_GATEWAY_PORT))

        device_id.clear.assert_called_once_with("gw-1")
        device_id.restore.assert_called_once_with(
            "gw-1", "r1", "network:router_gateway"
        )


class TestInterfaceSubport:
    def test_adds_subport_with_next_available_vlan(
        self, mocker, wiring, trunk_plugin, device_id
    ):
        next_vlan = mocker.patch.object(
            wiring, "_next_available_subport_vlan", return_value=201
        )
        trunk = {
            "id": "trunk-1",
            "sub_ports": [
                {
                    "port_id": "gw-1",
                    "segmentation_type": "vlan",
                    "segmentation_id": palo_alto_wiring.GATEWAY_SUBPORT_VLAN,
                }
            ],
        }

        wiring.add_interface_subport("r1", trunk, dict(_INTERFACE_PORT))

        next_vlan.assert_called_once_with(
            "r1", trunk, palo_alto_wiring.INTERFACE_SUBPORT_VLAN_START
        )
        trunk_plugin.add_subports.assert_called_once()
        _ctx, trunk_id, body = trunk_plugin.add_subports.call_args[0]
        assert trunk_id == "trunk-1"
        sub = body["sub_ports"][0]
        assert sub["port_id"] == "intf-1"
        assert sub["segmentation_type"] == "vlan"
        assert sub["segmentation_id"] == 201
        device_id.clear.assert_called_once_with("intf-1")
        device_id.restore.assert_called_once_with(
            "intf-1", "r1", "network:router_interface"
        )

    def test_add_subport_is_idempotent(self, mocker, wiring, trunk_plugin, device_id):
        next_vlan = mocker.patch.object(wiring, "_next_available_subport_vlan")
        trunk = {
            "id": "trunk-1",
            "sub_ports": [
                {
                    "port_id": "intf-1",
                    "segmentation_type": "vlan",
                    "segmentation_id": 201,
                }
            ],
        }

        wiring.add_interface_subport("r1", trunk, dict(_INTERFACE_PORT))

        next_vlan.assert_not_called()
        trunk_plugin.add_subports.assert_not_called()
        device_id.clear.assert_not_called()

    def test_vlan_exhaustion_raises_before_device_id_is_cleared(
        self, mocker, wiring, trunk_plugin, device_id
    ):
        mocker.patch.object(
            wiring,
            "_next_available_subport_vlan",
            side_effect=palo_alto_wiring.NoPaloAltoSubportVlanAvailable(
                router_id="r1", trunk_id="trunk-1", network_segment_ranges="200"
            ),
        )
        trunk = {"id": "trunk-1", "sub_ports": []}

        with pytest.raises(palo_alto_wiring.NoPaloAltoSubportVlanAvailable):
            wiring.add_interface_subport("r1", trunk, dict(_INTERFACE_PORT))

        trunk_plugin.add_subports.assert_not_called()
        device_id.clear.assert_not_called()
        device_id.restore.assert_not_called()


class TestSubportVlanAllocation:
    def _allowed_ranges(self, mocker, ranges):
        mocker.patch.object(
            palo_alto_wiring.utils,
            "allowed_tenant_vlan_id_ranges",
            return_value=ranges,
        )

    def test_starts_at_requested_vlan(self, mocker, wiring):
        self._allowed_ranges(mocker, [(1, 199), (200, 202)])
        trunk = {"id": "trunk-1", "sub_ports": []}

        assert (
            wiring._next_available_subport_vlan(
                "r1", trunk, palo_alto_wiring.INTERFACE_SUBPORT_VLAN_START
            )
            == 201
        )

    def test_skips_used_vlans(self, mocker, wiring):
        self._allowed_ranges(mocker, [(200, 202)])

        assert (
            wiring._next_available_subport_vlan(
                "r1",
                _TRUNK_USING_200_AND_201,
                palo_alto_wiring.INTERFACE_SUBPORT_VLAN_START,
            )
            == 202
        )

    def test_raises_when_no_vlan_available(self, mocker, wiring):
        self._allowed_ranges(mocker, [(200, 201)])

        with pytest.raises(palo_alto_wiring.NoPaloAltoSubportVlanAvailable):
            wiring._next_available_subport_vlan(
                "r1",
                _TRUNK_USING_200_AND_201,
                palo_alto_wiring.INTERFACE_SUBPORT_VLAN_START,
            )


class TestSubportRemoval:
    def test_remove_subport_when_present(self, wiring, trunk_plugin):
        trunk = {"id": "trunk-1", "sub_ports": [{"port_id": "gw-1"}]}

        wiring._remove_router_port_subport(trunk, "gw-1", "gateway")

        trunk_plugin.remove_subports.assert_called_once()
        _ctx, tid, body = trunk_plugin.remove_subports.call_args[0]
        assert tid == "trunk-1"
        assert body["sub_ports"] == [{"port_id": "gw-1"}]

    def test_remove_subport_idempotent(self, wiring, trunk_plugin):
        trunk = {"id": "trunk-1", "sub_ports": []}

        wiring._remove_router_port_subport(trunk, "gw-1", "gateway")

        trunk_plugin.remove_subports.assert_not_called()

    def test_remove_interface_subport_when_present(self, wiring, trunk_plugin):
        trunk = {"id": "trunk-1", "sub_ports": [{"port_id": "intf-1"}]}

        wiring._remove_router_port_subport(trunk, "intf-1", "interface")

        trunk_plugin.remove_subports.assert_called_once()
        _ctx, tid, body = trunk_plugin.remove_subports.call_args[0]
        assert tid == "trunk-1"
        assert body["sub_ports"] == [{"port_id": "intf-1"}]


class TestDeleteParentStack:
    def test_deletes_stack_when_no_subports_left(
        self, wiring, trunk_plugin, ironic, core_plugin, node
    ):
        # after removal the trunk has no subports -> delete trunk + parent
        trunk_plugin.get_trunk.return_value = {
            "id": "trunk-1",
            "port_id": "parent-1",
            "sub_ports": [],
        }

        wiring._delete_parent_stack_if_unused("r1", {"id": "trunk-1"})

        trunk_plugin.delete_trunk.assert_called_once()
        ironic.detach_vif_from_node.assert_called_once()
        core_plugin.delete_port.assert_called_once()
        _ctx, parent_id = core_plugin.delete_port.call_args[0]
        assert parent_id == "parent-1"

    def test_keeps_stack_when_subports_remain(
        self, wiring, trunk_plugin, ironic, core_plugin, node
    ):
        # a subnet subport still present -> leave trunk + parent alone
        trunk_plugin.get_trunk.return_value = {
            "id": "trunk-1",
            "port_id": "parent-1",
            "sub_ports": [{"port_id": "subnet-x"}],
        }

        wiring._delete_parent_stack_if_unused("r1", {"id": "trunk-1"})

        trunk_plugin.delete_trunk.assert_not_called()
        ironic.detach_vif_from_node.assert_not_called()
        core_plugin.delete_port.assert_not_called()


class TestCleanupAttachment:
    def test_deletes_orphan_parent_when_no_trunk(
        self, wiring, trunk_plugin, ironic, core_plugin, node
    ):
        # partial add left a parent port but no trunk
        trunk_plugin.get_trunks.return_value = []
        core_plugin.get_ports.return_value = [{"id": "parent-1"}]

        wiring.cleanup_attachment("r1", "gw-1", "gateway")

        ironic.detach_vif_from_node.assert_called_once()
        core_plugin.delete_port.assert_called_once()
        _ctx, parent_id = core_plugin.delete_port.call_args[0]
        assert parent_id == "parent-1"

    def test_noop_when_no_trunk_and_no_parent(
        self, wiring, trunk_plugin, ironic, core_plugin, node
    ):
        trunk_plugin.get_trunks.return_value = []
        core_plugin.get_ports.return_value = []

        wiring.cleanup_attachment("r1", "gw-1", "gateway")

        core_plugin.delete_port.assert_not_called()
        ironic.detach_vif_from_node.assert_not_called()
