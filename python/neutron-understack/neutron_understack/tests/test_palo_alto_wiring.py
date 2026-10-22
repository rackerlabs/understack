import logging
from types import SimpleNamespace
from unittest.mock import ANY

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

_PARENT = {"id": "parent-1"}


def _trunk(*port_ids):
    """Router r1's trunk on parent-1, carrying the given subport ports."""
    return {
        "id": "trunk-1",
        "port_id": "parent-1",
        "sub_ports": [{"port_id": port_id} for port_id in port_ids],
    }


def _snapshot(**changes):
    """Snapshot for interface port intf-1 on r1; by default nothing existed."""
    fields = {
        "router_id": "r1",
        "port_id": "intf-1",
        "label": "interface",
        "parent_id": None,
        "trunk_id": None,
        "subport_present": False,
        "parent_vif_attached": False,
    }
    return palo_alto_wiring.AttachmentSnapshot(**{**fields, **changes})


def _ironic_port(physical_network="physnet-1", local_link_connection=None):
    """An Ironic baremetal port; bindable unless a field is overridden empty."""
    if local_link_connection is None:
        local_link_connection = {"switch_id": "aa", "port_id": "Eth1/1"}
    return SimpleNamespace(
        physical_network=physical_network,
        local_link_connection=local_link_connection,
    )


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
            palo_alto_wiring.PaloAltoNodeHasNoUsablePort,
        ],
    )
    def test_wiring_errors_are_bad_request(self, exc):
        assert issubclass(exc, n_exc.BadRequest)


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


class TestCheckCanAttach:
    """The read-only check run before Neutron creates a gateway."""

    def test_passes_when_node_has_a_bindable_port(
        self, wiring, ironic, node, core_plugin, trunk_plugin
    ):
        ironic.node_ports.return_value = [
            _ironic_port(physical_network=None),
            _ironic_port(),
        ]

        wiring.check_can_attach("r1")

        ironic.node_ports.assert_called_once_with(node)
        # Nothing is created or attached: the check must have no side effects.
        ironic.attach_vif_to_node.assert_not_called()
        core_plugin.create_network.assert_not_called()
        core_plugin.create_port.assert_not_called()
        trunk_plugin.create_trunk.assert_not_called()

    @pytest.mark.parametrize(
        "ports",
        [
            [],
            [_ironic_port(physical_network=None)],
            [_ironic_port(local_link_connection={})],
        ],
        ids=["no-ports", "no-physical-network", "no-local-link-connection"],
    )
    def test_rejects_node_without_bindable_port(self, wiring, ironic, node, ports):
        ironic.node_ports.return_value = ports

        with pytest.raises(
            palo_alto_wiring.PaloAltoNodeHasNoUsablePort,
            match="node node-1 for Palo Alto router r1",
        ):
            wiring.check_can_attach("r1")


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

        m_parent.assert_called_once_with("r1", None)
        # VIF-attach runs on the parent BEFORE the trunk/subport
        m_vif.assert_called_once_with("r1", parent, None)
        # trunk + subport use the BOUND parent
        m_trunk.assert_called_once_with("r1", bound, None)
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


class TestDetachAndDeleteParent:
    def test_deletes_parent_even_when_node_is_gone(
        self, wiring, ironic, core_plugin, caplog
    ):
        # The port is still removed if the node can no longer be found by router.
        ironic.node_by_instance_uuid.return_value = None

        with caplog.at_level(logging.WARNING, logger=palo_alto_wiring.__name__):
            wiring._detach_and_delete_parent("r1", "parent-1")

        ironic.detach_vif_from_node.assert_not_called()
        core_plugin.delete_port.assert_called_once_with(ANY, "parent-1")
        assert "No node found for router r1" in caplog.text


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


class TestSnapshotAttachment:
    def test_treats_vif_as_detached_when_node_is_gone(
        self, wiring, core_plugin, trunk_plugin, ironic
    ):
        core_plugin.get_ports.return_value = [_PARENT]
        trunk_plugin.get_trunks.return_value = []
        ironic.node_by_instance_uuid.return_value = None

        assert wiring.snapshot_attachment("r1", "intf-1", "interface") == _snapshot(
            parent_id="parent-1"
        )
        ironic.node_vif_ids.assert_not_called()


class TestUndoAttachment:
    def test_keeps_subport_that_existed_before(
        self, wiring, core_plugin, trunk_plugin, ironic
    ):
        # Retrying an attach that already succeeded must not unwire the port.
        trunk_plugin.get_trunks.return_value = [_trunk("intf-1")]
        trunk_plugin.get_trunk.return_value = _trunk("intf-1")

        wiring.undo_attachment(
            _snapshot(
                parent_id="parent-1",
                trunk_id="trunk-1",
                subport_present=True,
                parent_vif_attached=True,
            )
        )

        trunk_plugin.remove_subports.assert_not_called()
        trunk_plugin.delete_trunk.assert_not_called()
        ironic.detach_vif_from_node.assert_not_called()
        core_plugin.delete_port.assert_not_called()

    def test_skips_vif_detach_when_node_is_gone(
        self, wiring, core_plugin, trunk_plugin, ironic
    ):
        core_plugin.get_ports.return_value = [_PARENT]
        trunk_plugin.get_trunks.return_value = []
        ironic.node_by_instance_uuid.return_value = None

        wiring.undo_attachment(_snapshot(parent_id="parent-1"))

        ironic.detach_vif_from_node.assert_not_called()
        core_plugin.delete_port.assert_not_called()


_ROLE_INSTANCE_INFO = {"traits": ["CUSTOM_NETDEV_ROLE_ATTACH"]}


def _nic(category, name):
    """A bindable Ironic NIC whose category is its port role."""
    return SimpleNamespace(
        name=name,
        category=category,
        physical_network="physnet-1",
        local_link_connection={"switch_id": "aa", "port_id": "Eth1/1"},
    )


_OUTSIDE_NIC = _nic("outside", "fw:ethernet1/19")
_INSIDE_NIC = _nic("inside", "fw:ethernet1/20")


def _named(by_name):
    """A get_ports/get_trunks fake returning what by_name holds for the name."""

    def lookup(_ctx, filters):
        return by_name.get(filters["name"][0], [])

    return lookup


class TestSingleStackWithoutPortRoles:
    def test_attach_uses_one_unsuffixed_stack_and_no_tags(
        self, mocker, wiring, ironic, node, core_plugin, trunk_plugin, device_id
    ):
        node.instance_info = {}
        ironic.node_vif_ids.return_value = []
        core_plugin.get_ports.return_value = []
        core_plugin.create_port.return_value = {"id": "parent-1"}
        core_plugin.get_port.return_value = _ANNOTATED_PARENT
        trunk_plugin.get_trunks.return_value = []
        trunk_plugin.create_trunk.return_value = {"id": "trunk-1", "sub_ports": []}
        tag_plugin = mocker.patch.object(wiring, "_tag_plugin")

        wiring.attach_port("r1", dict(_GATEWAY_PORT), "gateway")

        _ctx, body = core_plugin.create_port.call_args[0]
        assert body["port"]["name"] == "palo-alto-router-anchor-r1"
        ironic.attach_vif_to_node.assert_called_once_with(node, "parent-1")
        ironic.port_for_vif.assert_not_called()
        tag_plugin.assert_not_called()
        _ctx, body = trunk_plugin.create_trunk.call_args[0]
        assert body["trunk"]["name"] == "palo-alto-router-trunk-r1"


class TestSidedStacks:
    """A node with port roles gets one parent port and trunk per side."""

    @pytest.fixture(autouse=True)
    def _roles_node(self, mocker, wiring, ironic, core_plugin, trunk_plugin, device_id):
        self.node = mocker.Mock(id="node-1", instance_info=_ROLE_INSTANCE_INFO)
        ironic.node_by_instance_uuid.return_value = self.node
        ironic.node_vif_ids.return_value = []
        ironic.port_for_vif.side_effect = lambda _node, vif: {
            "parent-outside": _OUTSIDE_NIC,
            "parent-inside": _INSIDE_NIC,
        }.get(vif)
        core_plugin.get_ports.return_value = []
        core_plugin.create_port.side_effect = lambda _ctx, body: {
            "id": "parent-" + body["port"]["name"].rsplit("-", 1)[1]
        }
        core_plugin.get_port.side_effect = lambda _ctx, port_id: {
            **_ANNOTATED_PARENT,
            "id": port_id,
        }
        trunk_plugin.get_trunks.return_value = []
        trunk_plugin.create_trunk.side_effect = lambda _ctx, body: {
            "id": "trunk-" + body["trunk"]["name"].rsplit("-", 1)[1],
            "sub_ports": [],
        }
        mocker.patch.object(
            palo_alto_wiring.utils,
            "allowed_tenant_vlan_id_ranges",
            return_value=[(1, 1799)],
        )
        self.tags = mocker.patch.object(wiring, "_tag_plugin").return_value

    def test_gateway_goes_on_the_outside_stack(
        self, wiring, ironic, core_plugin, trunk_plugin
    ):
        wiring.attach_port("r1", dict(_GATEWAY_PORT), "gateway")

        _ctx, body = core_plugin.create_port.call_args[0]
        assert body["port"]["name"] == "palo-alto-router-anchor-r1-outside"
        self.tags.update_tags.assert_called_once_with(
            ANY, "ports", "parent-outside", {"tags": ["CUSTOM_NETDEV_OUTSIDE"]}
        )
        ironic.attach_vif_to_node.assert_called_once_with(
            self.node, "parent-outside", tags=["CUSTOM_NETDEV_OUTSIDE"]
        )
        _ctx, body = trunk_plugin.create_trunk.call_args[0]
        assert body["trunk"]["name"] == "palo-alto-router-trunk-r1-outside"
        assert body["trunk"]["port_id"] == "parent-outside"
        _ctx, trunk_id, body = trunk_plugin.add_subports.call_args[0]
        assert trunk_id == "trunk-outside"
        assert (
            body["sub_ports"][0]["segmentation_id"]
            == palo_alto_wiring.GATEWAY_SUBPORT_VLAN
        )

    def test_subnet_goes_on_the_inside_stack(
        self, wiring, ironic, core_plugin, trunk_plugin
    ):
        wiring.attach_port("r1", dict(_INTERFACE_PORT), "interface")

        _ctx, body = core_plugin.create_port.call_args[0]
        assert body["port"]["name"] == "palo-alto-router-anchor-r1-inside"
        self.tags.update_tags.assert_called_once_with(
            ANY, "ports", "parent-inside", {"tags": ["CUSTOM_NETDEV_INSIDE"]}
        )
        ironic.attach_vif_to_node.assert_called_once_with(
            self.node, "parent-inside", tags=["CUSTOM_NETDEV_INSIDE"]
        )
        _ctx, trunk_id, body = trunk_plugin.add_subports.call_args[0]
        assert trunk_id == "trunk-inside"
        assert (
            body["sub_ports"][0]["segmentation_id"]
            == palo_alto_wiring.INTERFACE_SUBPORT_VLAN_START
        )

    @pytest.mark.parametrize(
        ("landed", "where"),
        [(_INSIDE_NIC, "NIC fw:ethernet1/20"), (None, "no NIC")],
        ids=["wrong-nic", "no-nic"],
    )
    def test_rejects_a_vif_that_missed_its_sides_nic(
        self, wiring, ironic, trunk_plugin, landed, where
    ):
        ironic.port_for_vif.side_effect = None
        ironic.port_for_vif.return_value = landed

        with pytest.raises(
            palo_alto_wiring.PaloAltoParentNotOnSideNic,
            match=f"outside parent port parent-outside was attached to {where},",
        ):
            wiring.attach_port("r1", dict(_GATEWAY_PORT), "gateway")
        trunk_plugin.create_trunk.assert_not_called()

    def test_check_can_attach_needs_the_sides_nic(self, wiring, ironic):
        ironic.node_ports.return_value = [_INSIDE_NIC]

        with pytest.raises(
            palo_alto_wiring.PaloAltoNodeHasNoSideNic,
            match="no baremetal port with category outside",
        ):
            wiring.check_can_attach("r1")

        ironic.node_ports.return_value = [_INSIDE_NIC, _OUTSIDE_NIC]
        wiring.check_can_attach("r1")

    def test_snapshot_records_the_side(self, wiring, core_plugin, trunk_plugin):
        snapshot = wiring.snapshot_attachment("r1", "gw-1", "gateway")

        assert snapshot.side == "outside"
        assert core_plugin.get_ports.call_args.kwargs["filters"]["name"] == [
            "palo-alto-router-anchor-r1-outside"
        ]
        assert trunk_plugin.get_trunks.call_args.kwargs["filters"]["name"] == [
            "palo-alto-router-trunk-r1-outside"
        ]

    def test_cleanup_only_touches_the_sides_stack(
        self, wiring, ironic, core_plugin, trunk_plugin
    ):
        outside = {
            "id": "trunk-outside",
            "port_id": "parent-outside",
            "sub_ports": [{"port_id": "gw-1"}],
        }
        trunk_plugin.get_trunks.side_effect = _named(
            {"palo-alto-router-trunk-r1-outside": [outside]}
        )
        trunk_plugin.get_trunk.return_value = {**outside, "sub_ports": []}

        wiring.cleanup_attachment("r1", "gw-1", "gateway")

        _ctx, trunk_id, _body = trunk_plugin.remove_subports.call_args[0]
        assert trunk_id == "trunk-outside"
        trunk_plugin.delete_trunk.assert_called_once_with(ANY, "trunk-outside")
        ironic.detach_vif_from_node.assert_called_once_with(self.node, "parent-outside")
        core_plugin.delete_port.assert_called_once_with(ANY, "parent-outside")

    def test_cleanup_still_finds_a_single_stack_router(self, wiring, trunk_plugin):
        # A router built before the node had port roles keeps its one stack.
        single = {
            "id": "trunk-1",
            "port_id": "parent-1",
            "sub_ports": [{"port_id": "gw-1"}],
        }
        trunk_plugin.get_trunks.side_effect = _named(
            {"palo-alto-router-trunk-r1": [single]}
        )
        trunk_plugin.get_trunk.return_value = {**single, "sub_ports": []}

        wiring.cleanup_attachment("r1", "gw-1", "gateway")

        _ctx, trunk_id, _body = trunk_plugin.remove_subports.call_args[0]
        assert trunk_id == "trunk-1"

    def test_undo_removes_only_this_sides_new_stack(
        self, wiring, core_plugin, trunk_plugin
    ):
        # The inside attach failed after building its stack; outside is untouched.
        inside = {
            "id": "trunk-inside",
            "port_id": "parent-inside",
            "sub_ports": [{"port_id": "intf-1"}],
        }
        trunk_plugin.get_trunks.side_effect = _named(
            {"palo-alto-router-trunk-r1-inside": [inside]}
        )
        trunk_plugin.get_trunk.return_value = {**inside, "sub_ports": []}
        core_plugin.get_ports.side_effect = _named(
            {"palo-alto-router-anchor-r1-inside": [{"id": "parent-inside"}]}
        )

        wiring.undo_attachment(_snapshot(side="inside"))

        trunk_plugin.delete_trunk.assert_called_once_with(ANY, "trunk-inside")
        core_plugin.delete_port.assert_called_once_with(ANY, "parent-inside")
