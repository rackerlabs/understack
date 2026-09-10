import copy
from types import MethodType
from types import SimpleNamespace

import pytest
from neutron.db import l3_db
from neutron.services.trunk import rules as trunk_rules
from neutron_lib import constants as const
from neutron_lib import exceptions as n_exc
from neutron_lib.callbacks import events
from neutron_lib.callbacks import exceptions as callback_exc
from neutron_lib.callbacks import manager
from neutron_lib.callbacks import priority_group
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.exceptions import l3 as l3_exc

from neutron_understack.l3_router import palo_alto


@pytest.fixture(autouse=True)
def _isolated_callbacks(mocker):
    mocker.patch.object(registry, "_CALLBACK_MANAGER", manager.CallbacksManager())


class FakeFlavorPlugin:
    def __init__(self, driver, service_profiles=None, profiles=None):
        self.driver = driver
        self._service_profiles = service_profiles or []
        self._profiles = profiles or {}

    def get_flavor(self, _context, flavor_id):
        return {"id": flavor_id, "service_profiles": self._service_profiles}

    def get_flavor_next_provider(self, _context, _flavor_id):
        return [{"driver": self.driver}]

    def get_service_profile(self, _context, sp_id):
        return self._profiles[sp_id]


class FakePayload:
    def __init__(self, router, context="context"):
        self.states = (router,)
        self.context = context
        self.resource_id = router.get("id")


def _palo_alto_driver():
    return f"{palo_alto.PaloAlto.__module__}.{palo_alto.PaloAlto.__name__}"


def _make_provider(mocker, flavor_plugin, ironic=None, core_plugin=None):
    # directory.get_plugin(FLAVORS) -> flavor plugin (also pre-cached below);
    # directory.get_plugin() with no args -> core plugin (anchor network).
    mocker.patch.object(
        palo_alto.directory,
        "get_plugin",
        side_effect=lambda *a: flavor_plugin if a else core_plugin,
    )
    # get_admin_context() would init oslo policy; not needed for these tests.
    mocker.patch.object(palo_alto.n_context, "get_admin_context")
    provider = palo_alto.PaloAlto(mocker.Mock())
    provider._flavor_plugin_ref = flavor_plugin
    if ironic is not None:
        provider._ironic_ref = ironic
    return provider


class TestMetainfoParsing:
    def test_parses_json_string(self):
        assert _parse('{"resource_class": "BLAH"}') == {"resource_class": "BLAH"}

    def test_accepts_dict(self):
        assert _parse({"resource_class": "BLAH"}) == {"resource_class": "BLAH"}

    @pytest.mark.parametrize("raw", [None, "", "not-json", "[1, 2]"])
    def test_returns_empty_for_bad_input(self, raw):
        assert _parse(raw) == {}


def _parse(raw):
    return palo_alto._parse_metainfo(raw)


class TestPaloAltoProvider:
    def test_flavor_plugin_is_cached(self, mocker):
        plugin = FakeFlavorPlugin(_palo_alto_driver())
        get_plugin = mocker.patch.object(
            palo_alto.directory, "get_plugin", return_value=plugin
        )
        provider = palo_alto.PaloAlto(None)

        assert provider._flavor_plugin is plugin
        assert provider._flavor_plugin is plugin
        get_plugin.assert_called_once_with(palo_alto.plugin_constants.FLAVORS)

    def test_is_palo_alto_provider_returns_false_without_flavor(self, mocker):
        get_plugin = mocker.patch.object(palo_alto.directory, "get_plugin")
        provider = palo_alto.PaloAlto(None)

        assert provider._is_palo_alto_provider("context", {"id": "router-a"}) is False
        assert (
            provider._is_palo_alto_provider(
                "context",
                {"id": "router-a", "flavor_id": const.ATTR_NOT_SPECIFIED},
            )
            is False
        )
        get_plugin.assert_not_called()

    def test_is_palo_alto_provider_returns_true_for_palo_alto_driver(self, mocker):
        plugin = FakeFlavorPlugin(_palo_alto_driver())
        mocker.patch.object(palo_alto.directory, "get_plugin", return_value=plugin)
        provider = palo_alto.PaloAlto(None)

        assert (
            provider._is_palo_alto_provider(
                "context",
                {"id": "router-a", "flavor_id": "palo-alto-flavor-id"},
            )
            is True
        )

    def test_is_palo_alto_provider_returns_false_for_different_driver(self, mocker):
        plugin = FakeFlavorPlugin("neutron_understack.l3_router.vrf.Vrf")
        mocker.patch.object(palo_alto.directory, "get_plugin", return_value=plugin)
        provider = palo_alto.PaloAlto(None)

        assert (
            provider._is_palo_alto_provider(
                "context",
                {"id": "router-a", "flavor_id": "vrf-flavor-id"},
            )
            is False
        )


class TestExceptionHttpCodes:
    """Exceptions must map to real HTTP codes, not 500.

    neutron's FAULT_MAP maps Conflict->409 and BadRequest->400; the base
    NeutronException falls through to 500.
    """

    def test_no_node_available_is_conflict(self):
        assert issubclass(palo_alto.NoNetdevNodeAvailable, n_exc.Conflict)

    def test_flavor_misconfigured_is_bad_request(self):
        assert issubclass(palo_alto.PaloAltoFlavorMisconfigured, n_exc.BadRequest)

    def test_no_subport_vlan_available_is_conflict(self):
        assert issubclass(palo_alto.NoPaloAltoSubportVlanAvailable, n_exc.Conflict)


class TestResourceClassLookup:
    def test_reads_resource_class_from_profile_metainfo(self, mocker):
        plugin = FakeFlavorPlugin(
            _palo_alto_driver(),
            service_profiles=["sp1"],
            profiles={"sp1": {"metainfo": '{"resource_class": "PA-FW"}'}},
        )
        provider = _make_provider(mocker, plugin)
        rc = provider._resource_class_for_router("ctx", {"id": "r1", "flavor_id": "f1"})
        assert rc == "PA-FW"

    def test_raises_when_no_resource_class(self, mocker):
        plugin = FakeFlavorPlugin(
            _palo_alto_driver(),
            service_profiles=["sp1"],
            profiles={"sp1": {"metainfo": "{}"}},
        )
        provider = _make_provider(mocker, plugin)
        with pytest.raises(palo_alto.PaloAltoFlavorMisconfigured):
            provider._resource_class_for_router("ctx", {"id": "r1", "flavor_id": "f1"})


def _router():
    return {
        "id": "router-uuid",
        "name": "my-router",
        "project_id": "proj-1",
        "flavor_id": "f1",
    }


def _adopting_plugin():
    return FakeFlavorPlugin(
        _palo_alto_driver(),
        service_profiles=["sp1"],
        profiles={"sp1": {"metainfo": '{"resource_class": "PA-FW"}'}},
    )


class TestRouterCreate:
    """Adoption happens on the cancellable BEFORE_CREATE event.

    The router UUID is pre-generated there, so the handler validates *and*
    adopts. Any failure raises out of a cancellable event, so the router is
    never created without hardware.
    """

    def test_adopts_node_and_creates_anchor_network(self, mocker):
        ironic = mocker.Mock()
        node = mocker.Mock(id="node-uuid")
        ironic.available_node_for_resource_class.return_value = node
        core_plugin = mocker.Mock()
        core_plugin.get_networks.return_value = []

        provider = _make_provider(
            mocker, _adopting_plugin(), ironic=ironic, core_plugin=core_plugin
        )
        provider._process_router_create(
            "router", "before_create", "trigger", FakePayload(_router())
        )

        ironic.available_node_for_resource_class.assert_called_once_with("PA-FW")
        core_plugin.create_network.assert_called_once()
        # project_id must be supplied explicitly when calling the core plugin
        # directly (the API layer would otherwise fill it in).
        _ctx, body = core_plugin.create_network.call_args[0]
        # Direct plugin call skips API-layer extension defaults, so we must
        # supply project_id and router:external (the latter is read by the
        # auto_allocate NETWORK-create callback).
        assert "project_id" in body["network"]
        assert body["network"]["router:external"] is False
        ironic.adopt_node_for_router.assert_called_once_with(
            node,
            project_id="proj-1",
            router_id="router-uuid",
            router_name="my-router",
        )

    def test_reuses_existing_anchor_network(self, mocker):
        ironic = mocker.Mock()
        ironic.available_node_for_resource_class.return_value = mocker.Mock(id="n1")
        core_plugin = mocker.Mock()
        core_plugin.get_networks.return_value = [{"id": "existing-net"}]

        provider = _make_provider(
            mocker, _adopting_plugin(), ironic=ironic, core_plugin=core_plugin
        )
        provider._process_router_create(
            "router", "before_create", "trigger", FakePayload(_router())
        )

        core_plugin.create_network.assert_not_called()

    def test_raises_when_no_node_available(self, mocker):
        ironic = mocker.Mock()
        ironic.available_node_for_resource_class.return_value = None
        core_plugin = mocker.Mock()

        provider = _make_provider(
            mocker, _adopting_plugin(), ironic=ironic, core_plugin=core_plugin
        )
        with pytest.raises(palo_alto.NoNetdevNodeAvailable):
            provider._process_router_create(
                "router", "before_create", "trigger", FakePayload(_router())
            )
        ironic.adopt_node_for_router.assert_not_called()
        core_plugin.create_network.assert_not_called()

    def test_raises_when_flavor_misconfigured(self, mocker):
        plugin = FakeFlavorPlugin(
            _palo_alto_driver(),
            service_profiles=["sp1"],
            profiles={"sp1": {"metainfo": "{}"}},
        )
        ironic = mocker.Mock()
        provider = _make_provider(mocker, plugin, ironic=ironic)

        with pytest.raises(palo_alto.PaloAltoFlavorMisconfigured):
            provider._process_router_create(
                "router", "before_create", "trigger", FakePayload(_router())
            )
        ironic.available_node_for_resource_class.assert_not_called()

    def test_propagates_adopt_failure(self, mocker):
        # adopt_node_for_router rolls the node back internally, then re-raises;
        # because this is BEFORE_CREATE the raise aborts the router create.
        ironic = mocker.Mock()
        ironic.available_node_for_resource_class.return_value = mocker.Mock(id="n1")
        ironic.adopt_node_for_router.side_effect = RuntimeError("boom")
        core_plugin = mocker.Mock()
        core_plugin.get_networks.return_value = []

        provider = _make_provider(
            mocker, _adopting_plugin(), ironic=ironic, core_plugin=core_plugin
        )
        with pytest.raises(RuntimeError):
            provider._process_router_create(
                "router", "before_create", "trigger", FakePayload(_router())
            )

    def test_skips_non_palo_alto_router(self, mocker):
        ironic = mocker.Mock()
        plugin = FakeFlavorPlugin("neutron_understack.l3_router.vrf.Vrf")
        provider = _make_provider(mocker, plugin, ironic=ironic)

        provider._process_router_create(
            "router", "before_create", "trigger", FakePayload(_router())
        )
        ironic.available_node_for_resource_class.assert_not_called()


class TestRouterDelete:
    def _router(self):
        return {"id": "router-uuid", "name": "my-router", "flavor_id": "f1"}

    def test_releases_adopted_node(self, mocker):
        ironic = mocker.Mock()
        ironic.release_node_for_router.return_value = mocker.Mock(id="node-uuid")
        provider = _make_provider(
            mocker, FakeFlavorPlugin(_palo_alto_driver()), ironic=ironic
        )

        provider._process_router_delete(
            "router", "after_delete", "trigger", FakePayload(self._router())
        )
        ironic.release_node_for_router.assert_called_once_with("router-uuid")

    def test_warns_when_no_node_bound(self, mocker):
        ironic = mocker.Mock()
        ironic.release_node_for_router.return_value = None
        provider = _make_provider(
            mocker, FakeFlavorPlugin(_palo_alto_driver()), ironic=ironic
        )

        # Should not raise even though nothing was released.
        provider._process_router_delete(
            "router", "after_delete", "trigger", FakePayload(self._router())
        )

    def test_skips_non_palo_alto_router(self, mocker):
        ironic = mocker.Mock()
        plugin = FakeFlavorPlugin("neutron_understack.l3_router.vrf.Vrf")
        provider = _make_provider(mocker, plugin, ironic=ironic)

        provider._process_router_delete(
            "router", "after_delete", "trigger", FakePayload(self._router())
        )
        ironic.release_node_for_router.assert_not_called()


class TestGatewayLookups:
    def test_names_are_deterministic(self, mocker):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        assert provider._parent_port_name("r1") == "palo-alto-router-anchor-r1"
        assert provider._trunk_name("r1") == "palo-alto-router-trunk-r1"

    def test_trunk_plugin_delegates_to_utils(self, mocker):
        tp = mocker.Mock()
        mocker.patch.object(palo_alto.utils, "fetch_trunk_plugin", return_value=tp)
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        assert provider._trunk_plugin is tp

    def test_gateway_port_found_filters_by_owner_and_router(self, mocker):
        core_plugin = mocker.Mock()
        core_plugin.get_ports.return_value = [{"id": "gw-1"}]
        provider = _make_provider(
            mocker, FakeFlavorPlugin(_palo_alto_driver()), core_plugin=core_plugin
        )

        assert provider._gateway_port_for_router("r1") == {"id": "gw-1"}
        _args, kwargs = core_plugin.get_ports.call_args
        assert kwargs["filters"]["device_id"] == ["r1"]
        assert kwargs["filters"]["device_owner"] == ["network:router_gateway"]

    def test_gateway_port_none_when_absent(self, mocker):
        core_plugin = mocker.Mock()
        core_plugin.get_ports.return_value = []
        provider = _make_provider(
            mocker, FakeFlavorPlugin(_palo_alto_driver()), core_plugin=core_plugin
        )
        assert provider._gateway_port_for_router("r1") is None


class TestParentPort:
    def _core_plugin(self, mocker, ports):
        core = mocker.Mock()
        core.get_networks.return_value = [{"id": "anchor-net"}]  # anchor exists
        core.get_ports.return_value = ports
        core.create_port.return_value = {"id": "parent-new"}
        return core

    def test_creates_parent_when_absent(self, mocker):
        core = self._core_plugin(mocker, ports=[])
        provider = _make_provider(
            mocker, FakeFlavorPlugin(_palo_alto_driver()), core_plugin=core
        )

        port = provider._ensure_parent_port({"id": "r1"})

        assert port == {"id": "parent-new"}
        core.create_port.assert_called_once()
        _ctx, body = core.create_port.call_args[0]
        net = body["port"]
        assert net["name"] == "palo-alto-router-anchor-r1"
        assert net["network_id"] == "anchor-net"
        assert net["binding:vnic_type"] == "baremetal"
        assert net["device_id"] == "r1"

    def test_reuses_existing_parent(self, mocker):
        core = self._core_plugin(mocker, ports=[{"id": "parent-existing"}])
        provider = _make_provider(
            mocker, FakeFlavorPlugin(_palo_alto_driver()), core_plugin=core
        )

        port = provider._ensure_parent_port({"id": "r1"})

        assert port == {"id": "parent-existing"}
        core.create_port.assert_not_called()


_ANNOTATED_PARENT = {
    "id": "parent-1",
    "binding:host_id": "node-1",
    "binding:profile": {
        "physical_network": "n11-22-network",
        "local_link_information": [{"switch_id": "aa", "port_id": "Eth1/1"}],
    },
}


class TestParentVifAttach:
    def _provider(self, mocker, node, vif_ids, fresh_port=None):
        ironic = mocker.Mock()
        ironic.node_by_instance_uuid.return_value = node
        ironic.node_vif_ids.return_value = vif_ids
        core = mocker.Mock()
        core.get_port.return_value = fresh_port or _ANNOTATED_PARENT
        provider = _make_provider(
            mocker,
            FakeFlavorPlugin(_palo_alto_driver()),
            ironic=ironic,
            core_plugin=core,
        )
        return provider, ironic

    def test_attaches_when_not_already(self, mocker):
        node = mocker.Mock(id="node-1")
        provider, ironic = self._provider(mocker, node, vif_ids=[])

        result = provider._ensure_parent_vif_attached({"id": "r1"}, {"id": "parent-1"})

        ironic.attach_vif_to_node.assert_called_once_with(node, "parent-1")
        assert result == _ANNOTATED_PARENT  # fresh, annotated copy returned

    def test_recovers_when_attach_raises_after_vif_lands(self, mocker):
        node = mocker.Mock(id="node-1")
        provider, ironic = self._provider(mocker, node, vif_ids=[])
        ironic.node_vif_ids.side_effect = [[], ["parent-1"]]
        ironic.attach_vif_to_node.side_effect = RuntimeError("rpc timeout")

        result = provider._ensure_parent_vif_attached({"id": "r1"}, {"id": "parent-1"})

        ironic.attach_vif_to_node.assert_called_once_with(node, "parent-1")
        assert result == _ANNOTATED_PARENT

    def test_reraises_attach_error_when_vif_did_not_land(self, mocker):
        node = mocker.Mock(id="node-1")
        provider, ironic = self._provider(mocker, node, vif_ids=[])
        ironic.node_vif_ids.side_effect = [[], []]
        ironic.attach_vif_to_node.side_effect = RuntimeError("rpc timeout")

        with pytest.raises(RuntimeError, match="rpc timeout"):
            provider._ensure_parent_vif_attached({"id": "r1"}, {"id": "parent-1"})

    def test_skips_attach_when_already_attached(self, mocker):
        node = mocker.Mock(id="node-1")
        provider, ironic = self._provider(mocker, node, vif_ids=["parent-1"])

        provider._ensure_parent_vif_attached({"id": "r1"}, {"id": "parent-1"})

        ironic.attach_vif_to_node.assert_not_called()

    def test_raises_when_no_adopted_node(self, mocker):
        provider, ironic = self._provider(mocker, node=None, vif_ids=[])

        with pytest.raises(n_exc.BadRequest):
            provider._ensure_parent_vif_attached({"id": "r1"}, {"id": "parent-1"})
        ironic.attach_vif_to_node.assert_not_called()

    def test_raises_when_parent_not_annotated(self, mocker):
        # e.g. the enrolled baremetal port had no physical_network
        node = mocker.Mock(id="node-1")
        unannotated = {"id": "parent-1", "binding:host_id": "", "binding:profile": {}}
        provider, _ = self._provider(mocker, node, vif_ids=[], fresh_port=unannotated)

        with pytest.raises(n_exc.BadRequest):
            provider._ensure_parent_vif_attached({"id": "r1"}, {"id": "parent-1"})


class TestTrunk:
    def _provider_with_trunk(self, mocker, existing_trunks):
        tp = mocker.Mock()
        tp.get_trunks.return_value = existing_trunks
        tp.create_trunk.return_value = {"id": "trunk-new"}
        mocker.patch.object(palo_alto.utils, "fetch_trunk_plugin", return_value=tp)
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        return provider, tp

    def test_creates_trunk_when_absent(self, mocker):
        provider, tp = self._provider_with_trunk(mocker, existing_trunks=[])

        trunk = provider._ensure_trunk({"id": "r1"}, {"id": "parent-1"})

        assert trunk == {"id": "trunk-new"}
        tp.create_trunk.assert_called_once()
        _ctx, body = tp.create_trunk.call_args[0]
        assert body["trunk"]["name"] == "palo-alto-router-trunk-r1"
        assert body["trunk"]["port_id"] == "parent-1"
        assert body["trunk"]["sub_ports"] == []

    def test_reuses_existing_trunk(self, mocker):
        provider, tp = self._provider_with_trunk(
            mocker, existing_trunks=[{"id": "trunk-existing"}]
        )

        trunk = provider._ensure_trunk({"id": "r1"}, {"id": "parent-1"})

        assert trunk == {"id": "trunk-existing"}
        tp.create_trunk.assert_not_called()


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


class TestGatewaySubport:
    def _provider(self, mocker):
        tp = mocker.Mock()
        tp.add_subports.return_value = {"id": "trunk-1", "updated": True}
        mocker.patch.object(palo_alto.utils, "fetch_trunk_plugin", return_value=tp)
        self.clear = mocker.patch.object(palo_alto.utils, "clear_device_id_for_port")
        self.restore = mocker.patch.object(
            palo_alto.utils, "set_device_id_and_owner_for_port"
        )
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        return provider, tp

    def test_adds_subport_with_fixed_vlan(self, mocker):
        provider, tp = self._provider(mocker)
        trunk = {"id": "trunk-1", "sub_ports": []}

        provider._add_gateway_subport({"id": "r1"}, trunk, dict(_GATEWAY_PORT))

        tp.add_subports.assert_called_once()
        _ctx, trunk_id, body = tp.add_subports.call_args[0]
        assert trunk_id == "trunk-1"
        sub = body["sub_ports"][0]
        assert sub["port_id"] == "gw-1"
        assert sub["segmentation_type"] == "vlan"
        assert sub["segmentation_id"] == palo_alto.GATEWAY_SUBPORT_VLAN
        # device_id cleared for the add (trunk validator rejects it) and restored
        self.clear.assert_called_once_with("gw-1")
        self.restore.assert_called_once_with("gw-1", "r1", "network:router_gateway")

    def test_add_subport_is_idempotent(self, mocker):
        provider, tp = self._provider(mocker)
        trunk = {
            "id": "trunk-1",
            "sub_ports": [
                {
                    "port_id": "gw-1",
                    "segmentation_id": palo_alto.GATEWAY_SUBPORT_VLAN,
                }
            ],
        }

        provider._add_gateway_subport({"id": "r1"}, trunk, dict(_GATEWAY_PORT))

        tp.add_subports.assert_not_called()
        self.clear.assert_not_called()


class TestSubportVlanAllocation:
    def _provider(self, mocker, ranges):
        mocker.patch.object(
            palo_alto.utils,
            "allowed_tenant_vlan_id_ranges",
            return_value=ranges,
        )
        return _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))

    def test_starts_at_requested_vlan(self, mocker):
        provider = self._provider(mocker, ranges=[(1, 199), (200, 202)])
        trunk = {"id": "trunk-1", "sub_ports": []}

        assert (
            provider._next_available_subport_vlan(
                "r1", trunk, palo_alto.INTERFACE_SUBPORT_VLAN_START
            )
            == 201
        )

    def test_skips_used_vlans(self, mocker):
        provider = self._provider(mocker, ranges=[(200, 202)])
        trunk = {
            "id": "trunk-1",
            "sub_ports": [
                {
                    "port_id": "gw-1",
                    "segmentation_type": "vlan",
                    "segmentation_id": 200,
                },
                {
                    "port_id": "intf-1",
                    "segmentation_type": "vlan",
                    "segmentation_id": 201,
                },
            ],
        }

        assert (
            provider._next_available_subport_vlan(
                "r1", trunk, palo_alto.INTERFACE_SUBPORT_VLAN_START
            )
            == 202
        )

    def test_raises_when_no_vlan_available(self, mocker):
        provider = self._provider(mocker, ranges=[(200, 201)])
        trunk = {
            "id": "trunk-1",
            "sub_ports": [
                {
                    "port_id": "gw-1",
                    "segmentation_type": "vlan",
                    "segmentation_id": 200,
                },
                {
                    "port_id": "intf-1",
                    "segmentation_type": "vlan",
                    "segmentation_id": 201,
                },
            ],
        }

        with pytest.raises(palo_alto.NoPaloAltoSubportVlanAvailable):
            provider._next_available_subport_vlan(
                "r1", trunk, palo_alto.INTERFACE_SUBPORT_VLAN_START
            )


class TestInterfaceSubport:
    def _provider(self, mocker):
        tp = mocker.Mock()
        tp.add_subports.return_value = {"id": "trunk-1", "updated": True}
        mocker.patch.object(palo_alto.utils, "fetch_trunk_plugin", return_value=tp)
        self.clear = mocker.patch.object(palo_alto.utils, "clear_device_id_for_port")
        self.restore = mocker.patch.object(
            palo_alto.utils, "set_device_id_and_owner_for_port"
        )
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        return provider, tp

    def test_adds_subport_with_next_available_vlan(self, mocker):
        provider, tp = self._provider(mocker)
        next_vlan = mocker.patch.object(
            provider, "_next_available_subport_vlan", return_value=201
        )
        trunk = {
            "id": "trunk-1",
            "sub_ports": [
                {
                    "port_id": "gw-1",
                    "segmentation_type": "vlan",
                    "segmentation_id": palo_alto.GATEWAY_SUBPORT_VLAN,
                }
            ],
        }

        provider._add_interface_subport({"id": "r1"}, trunk, dict(_INTERFACE_PORT))

        next_vlan.assert_called_once_with(
            "r1", trunk, palo_alto.INTERFACE_SUBPORT_VLAN_START
        )
        tp.add_subports.assert_called_once()
        _ctx, trunk_id, body = tp.add_subports.call_args[0]
        assert trunk_id == "trunk-1"
        sub = body["sub_ports"][0]
        assert sub["port_id"] == "intf-1"
        assert sub["segmentation_type"] == "vlan"
        assert sub["segmentation_id"] == 201
        self.clear.assert_called_once_with("intf-1")
        self.restore.assert_called_once_with("intf-1", "r1", "network:router_interface")

    def test_add_subport_is_idempotent(self, mocker):
        provider, tp = self._provider(mocker)
        next_vlan = mocker.patch.object(provider, "_next_available_subport_vlan")
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

        provider._add_interface_subport({"id": "r1"}, trunk, dict(_INTERFACE_PORT))

        next_vlan.assert_not_called()
        tp.add_subports.assert_not_called()
        self.clear.assert_not_called()


class TestGatewayCreateHandler:
    def _payload(self, mocker, router_id="r1"):
        payload = mocker.Mock()
        payload.context = "ctx"
        payload.resource_id = router_id
        return payload

    def test_orchestrates_in_order(self, mocker):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        router = {"id": "r1", "flavor_id": "f1"}
        provider.l3plugin.get_router.return_value = router
        mocker.patch.object(provider, "_is_palo_alto_provider", return_value=True)
        mocker.patch.object(
            provider, "_gateway_port_for_router", return_value={"id": "gw-1"}
        )
        parent = {"id": "parent-1"}
        bound = {"id": "parent-1", "bound": True}
        trunk = {"id": "trunk-1"}
        m_parent = mocker.patch.object(
            provider, "_ensure_parent_port", return_value=parent
        )
        m_vif = mocker.patch.object(
            provider, "_ensure_parent_vif_attached", return_value=bound
        )
        m_trunk = mocker.patch.object(provider, "_ensure_trunk", return_value=trunk)
        m_sub = mocker.patch.object(provider, "_add_gateway_subport")

        provider._process_gateway_create("r", "e", "t", self._payload(mocker))

        m_parent.assert_called_once_with(router)
        # VIF-attach runs on the parent BEFORE the trunk/subport
        m_vif.assert_called_once_with(router, parent)
        # trunk + subport use the BOUND parent
        m_trunk.assert_called_once_with(router, bound)
        m_sub.assert_called_once_with(router, trunk, {"id": "gw-1"})

    def test_skips_non_palo_alto_router(self, mocker):
        provider = _make_provider(
            mocker, FakeFlavorPlugin("neutron_understack.l3_router.vrf.Vrf")
        )
        provider.l3plugin.get_router.return_value = {"id": "r1", "flavor_id": "f1"}
        m_parent = mocker.patch.object(provider, "_ensure_parent_port")

        provider._process_gateway_create("r", "e", "t", self._payload(mocker))

        m_parent.assert_not_called()

    def test_raises_when_gateway_port_missing(self, mocker):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        provider.l3plugin.get_router.return_value = {"id": "r1", "flavor_id": "f1"}
        mocker.patch.object(provider, "_is_palo_alto_provider", return_value=True)
        mocker.patch.object(provider, "_gateway_port_for_router", return_value=None)

        with pytest.raises(n_exc.BadRequest):
            provider._process_gateway_create("r", "e", "t", self._payload(mocker))


class TestRouterInterfaceCreateHandler:
    def _payload(self, mocker, router_id="r1", port=None):
        payload = mocker.Mock()
        payload.context = "ctx"
        payload.resource_id = router_id
        payload.metadata = {"port": port if port is not None else dict(_INTERFACE_PORT)}
        return payload

    def test_orchestrates_in_order(self, mocker):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        router = {"id": "r1", "flavor_id": "f1"}
        provider.l3plugin.get_router.return_value = router
        mocker.patch.object(provider, "_is_palo_alto_provider", return_value=True)
        parent = {"id": "parent-1"}
        bound = {"id": "parent-1", "bound": True}
        trunk = {"id": "trunk-1"}
        m_parent = mocker.patch.object(
            provider, "_ensure_parent_port", return_value=parent
        )
        m_vif = mocker.patch.object(
            provider, "_ensure_parent_vif_attached", return_value=bound
        )
        m_trunk = mocker.patch.object(provider, "_ensure_trunk", return_value=trunk)
        m_sub = mocker.patch.object(provider, "_add_interface_subport")
        mocker.patch.object(provider, "_parent_port_for_router", return_value=None)
        mocker.patch.object(provider, "_trunk_for_router", return_value=None)

        provider._process_router_interface_create("r", "e", "t", self._payload(mocker))

        m_parent.assert_called_once_with(router)
        m_vif.assert_called_once_with(router, parent)
        m_trunk.assert_called_once_with(router, bound)
        m_sub.assert_called_once_with(router, trunk, dict(_INTERFACE_PORT))

    def test_skips_non_palo_alto_router(self, mocker):
        provider = _make_provider(
            mocker, FakeFlavorPlugin("neutron_understack.l3_router.vrf.Vrf")
        )
        provider.l3plugin.get_router.return_value = {"id": "r1", "flavor_id": "f1"}
        m_parent = mocker.patch.object(provider, "_ensure_parent_port")

        provider._process_router_interface_create("r", "e", "t", self._payload(mocker))

        m_parent.assert_not_called()

    def test_skips_non_router_interface_port(self, mocker):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        provider.l3plugin.get_router.return_value = {"id": "r1", "flavor_id": "f1"}
        mocker.patch.object(provider, "_is_palo_alto_provider", return_value=True)
        m_parent = mocker.patch.object(provider, "_ensure_parent_port")
        port = {**_INTERFACE_PORT, "device_owner": "network:dhcp"}

        provider._process_router_interface_create(
            "r", "e", "t", self._payload(mocker, port=port)
        )

        m_parent.assert_not_called()

    def test_raises_when_interface_port_missing(self, mocker):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        provider.l3plugin.get_router.return_value = {"id": "r1", "flavor_id": "f1"}
        mocker.patch.object(provider, "_is_palo_alto_provider", return_value=True)
        payload = self._payload(mocker, port=None)
        payload.metadata = {}

        with pytest.raises(n_exc.BadRequest):
            provider._process_router_interface_create("r", "e", "t", payload)


class TestGatewayTeardown:
    def _provider(self, mocker, trunk_after_removal):
        tp = mocker.Mock()
        tp.get_trunk.return_value = trunk_after_removal
        mocker.patch.object(palo_alto.utils, "fetch_trunk_plugin", return_value=tp)
        ironic = mocker.Mock()
        ironic.node_by_instance_uuid.return_value = mocker.Mock(id="node-1")
        core = mocker.Mock()
        provider = _make_provider(
            mocker,
            FakeFlavorPlugin(_palo_alto_driver()),
            ironic=ironic,
            core_plugin=core,
        )
        return provider, tp, ironic, core

    def test_remove_subport_when_present(self, mocker):
        provider, tp, _, _ = self._provider(mocker, trunk_after_removal={})
        trunk = {"id": "trunk-1", "sub_ports": [{"port_id": "gw-1"}]}

        provider._remove_gateway_subport(trunk, "gw-1")

        tp.remove_subports.assert_called_once()
        _ctx, tid, body = tp.remove_subports.call_args[0]
        assert tid == "trunk-1"
        assert body["sub_ports"] == [{"port_id": "gw-1"}]

    def test_remove_subport_idempotent(self, mocker):
        provider, tp, _, _ = self._provider(mocker, trunk_after_removal={})
        trunk = {"id": "trunk-1", "sub_ports": []}

        provider._remove_gateway_subport(trunk, "gw-1")

        tp.remove_subports.assert_not_called()

    def test_remove_interface_subport_when_present(self, mocker):
        provider, tp, _, _ = self._provider(mocker, trunk_after_removal={})
        trunk = {"id": "trunk-1", "sub_ports": [{"port_id": "intf-1"}]}

        provider._remove_interface_subport(trunk, "intf-1")

        tp.remove_subports.assert_called_once()
        _ctx, tid, body = tp.remove_subports.call_args[0]
        assert tid == "trunk-1"
        assert body["sub_ports"] == [{"port_id": "intf-1"}]

    def test_deletes_stack_when_no_subports_left(self, mocker):
        # after removal the trunk has no subports -> delete trunk + parent
        provider, tp, ironic, core = self._provider(
            mocker,
            trunk_after_removal={
                "id": "trunk-1",
                "port_id": "parent-1",
                "sub_ports": [],
            },
        )

        provider._delete_parent_stack_if_unused("r1", {"id": "trunk-1"})

        tp.delete_trunk.assert_called_once()
        ironic.detach_vif_from_node.assert_called_once()
        core.delete_port.assert_called_once()
        _ctx, parent_id = core.delete_port.call_args[0]
        assert parent_id == "parent-1"

    def test_keeps_stack_when_subports_remain(self, mocker):
        # a subnet subport still present -> leave trunk + parent alone
        provider, tp, ironic, core = self._provider(
            mocker,
            trunk_after_removal={
                "id": "trunk-1",
                "port_id": "parent-1",
                "sub_ports": [{"port_id": "subnet-x"}],
            },
        )

        provider._delete_parent_stack_if_unused("r1", {"id": "trunk-1"})

        tp.delete_trunk.assert_not_called()
        ironic.detach_vif_from_node.assert_not_called()
        core.delete_port.assert_not_called()


class TestGatewayDeleteHandler:
    def _payload(self, mocker, router_id="r1"):
        payload = mocker.Mock()
        payload.context = "ctx"
        payload.resource_id = router_id
        return payload

    def test_cleans_up_when_palo_alto(self, mocker):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        router = {"id": "r1", "flavor_id": "f1"}
        provider.l3plugin.get_router.return_value = router
        mocker.patch.object(provider, "_is_palo_alto_provider", return_value=True)
        mocker.patch.object(
            provider, "_gateway_port_for_router", return_value={"id": "gw-1"}
        )
        m_cleanup = mocker.patch.object(provider, "_cleanup_gateway_attachment")

        provider._process_gateway_delete("r", "e", "t", self._payload(mocker))

        m_cleanup.assert_called_once_with(router, {"id": "gw-1"})

    def test_skips_non_palo_alto(self, mocker):
        provider = _make_provider(
            mocker, FakeFlavorPlugin("neutron_understack.l3_router.vrf.Vrf")
        )
        provider.l3plugin.get_router.return_value = {"id": "r1", "flavor_id": "f1"}
        m_cleanup = mocker.patch.object(provider, "_cleanup_gateway_attachment")

        provider._process_gateway_delete("r", "e", "t", self._payload(mocker))

        m_cleanup.assert_not_called()

    def test_skips_when_no_gateway_port(self, mocker):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        provider.l3plugin.get_router.return_value = {"id": "r1", "flavor_id": "f1"}
        mocker.patch.object(provider, "_is_palo_alto_provider", return_value=True)
        mocker.patch.object(provider, "_gateway_port_for_router", return_value=None)
        m_cleanup = mocker.patch.object(provider, "_cleanup_gateway_attachment")

        provider._process_gateway_delete("r", "e", "t", self._payload(mocker))

        m_cleanup.assert_not_called()


class TestRouterInterfacePortDeleteHandler:
    def _payload(self, mocker, port=None):
        mocker.patch.object(
            palo_alto.l3_obj.RouterPort, "objects_exist", return_value=True
        )
        payload = mocker.Mock()
        payload.context = "ctx"
        payload.resource_id = "intf-1"
        payload.metadata = {
            "port": port if port is not None else dict(_INTERFACE_PORT),
            "port_check": False,
        }
        return payload

    @pytest.mark.parametrize("port_check", [True, None, "missing"])
    def test_skips_unless_l3_explicitly_authorized_removal(self, mocker, port_check):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        cleanup = mocker.patch.object(provider, "_cleanup_interface_attachment")
        payload = self._payload(mocker)
        if port_check == "missing":
            payload.metadata.pop("port_check")
        else:
            payload.metadata["port_check"] = port_check

        provider._process_router_interface_port_delete("r", "e", "t", payload)

        cleanup.assert_not_called()
        provider.l3plugin.get_router.assert_not_called()

    def test_cleans_up_before_port_delete_when_palo_alto(self, mocker):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        router = {"id": "r1", "flavor_id": "f1"}
        provider.l3plugin.get_router.return_value = router
        mocker.patch.object(provider, "_is_palo_alto_provider", return_value=True)
        m_cleanup = mocker.patch.object(provider, "_cleanup_interface_attachment")

        provider._process_router_interface_port_delete(
            "r", "e", "t", self._payload(mocker)
        )

        m_cleanup.assert_called_once_with(router, dict(_INTERFACE_PORT))

    def test_skips_non_router_interface_port(self, mocker):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        m_cleanup = mocker.patch.object(provider, "_cleanup_interface_attachment")
        port = {**_INTERFACE_PORT, "device_owner": "network:dhcp"}

        provider._process_router_interface_port_delete(
            "r", "e", "t", self._payload(mocker, port=port)
        )

        m_cleanup.assert_not_called()
        provider.l3plugin.get_router.assert_not_called()

    def test_skips_non_palo_alto_router(self, mocker):
        provider = _make_provider(
            mocker, FakeFlavorPlugin("neutron_understack.l3_router.vrf.Vrf")
        )
        provider.l3plugin.get_router.return_value = {"id": "r1", "flavor_id": "f1"}
        m_cleanup = mocker.patch.object(provider, "_cleanup_interface_attachment")

        provider._process_router_interface_port_delete(
            "r", "e", "t", self._payload(mocker)
        )

        m_cleanup.assert_not_called()

    def test_skips_when_router_lookup_fails(self, mocker):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        provider.l3plugin.get_router.side_effect = RuntimeError("db hiccup")
        m_cleanup = mocker.patch.object(provider, "_cleanup_interface_attachment")

        provider._process_router_interface_port_delete(
            "r", "e", "t", self._payload(mocker)
        )

        m_cleanup.assert_not_called()

    def test_skips_when_palo_alto_check_fails(self, mocker):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        provider.l3plugin.get_router.return_value = {"id": "r1", "flavor_id": "f1"}
        mocker.patch.object(
            provider,
            "_is_palo_alto_provider",
            side_effect=RuntimeError("flavor lookup failed"),
        )
        m_cleanup = mocker.patch.object(provider, "_cleanup_interface_attachment")

        provider._process_router_interface_port_delete(
            "r", "e", "t", self._payload(mocker)
        )

        m_cleanup.assert_not_called()

    def test_cleanup_error_still_raises_for_confirmed_palo_alto(self, mocker):
        provider = _make_provider(mocker, FakeFlavorPlugin(_palo_alto_driver()))
        router = {"id": "r1", "flavor_id": "f1"}
        provider.l3plugin.get_router.return_value = router
        mocker.patch.object(provider, "_is_palo_alto_provider", return_value=True)
        mocker.patch.object(
            provider,
            "_cleanup_interface_attachment",
            side_effect=RuntimeError("cleanup failed"),
        )

        with pytest.raises(RuntimeError, match="cleanup failed"):
            provider._process_router_interface_port_delete(
                "r", "e", "t", self._payload(mocker)
            )


class TestGatewayCleanupPartialAdd:
    def _provider(self, mocker, trunks, ports):
        tp = mocker.Mock()
        tp.get_trunks.return_value = trunks
        mocker.patch.object(palo_alto.utils, "fetch_trunk_plugin", return_value=tp)
        ironic = mocker.Mock()
        ironic.node_by_instance_uuid.return_value = mocker.Mock(id="node-1")
        core = mocker.Mock()
        core.get_networks.return_value = [{"id": "anchor-net"}]
        core.get_ports.return_value = ports
        provider = _make_provider(
            mocker,
            FakeFlavorPlugin(_palo_alto_driver()),
            ironic=ironic,
            core_plugin=core,
        )
        return provider, ironic, core

    def test_deletes_orphan_parent_when_no_trunk(self, mocker):
        # partial add left a parent port but no trunk
        provider, ironic, core = self._provider(
            mocker, trunks=[], ports=[{"id": "parent-1"}]
        )

        provider._cleanup_gateway_attachment({"id": "r1"}, {"id": "gw-1"})

        ironic.detach_vif_from_node.assert_called_once()
        core.delete_port.assert_called_once()
        _ctx, parent_id = core.delete_port.call_args[0]
        assert parent_id == "parent-1"

    def test_noop_when_no_trunk_and_no_parent(self, mocker):
        provider, ironic, core = self._provider(mocker, trunks=[], ports=[])

        provider._cleanup_gateway_attachment({"id": "r1"}, {"id": "gw-1"})

        core.delete_port.assert_not_called()
        ironic.detach_vif_from_node.assert_not_called()


@pytest.fixture
def interface_lifecycle(mocker):
    """Run Neutron's L3 flow/guards with stateful core, trunk and Ironic doubles."""
    state = SimpleNamespace(
        ports={}, trunks={}, vifs=set(), associations=set(), fail=None
    )

    def fail_at(stage):
        if state.fail == stage:
            raise RuntimeError(f"{stage} failed")

    core = mocker.Mock()
    trunk_plugin = mocker.Mock()
    ironic = mocker.Mock()
    context = mocker.Mock()
    context.session.is_active = True
    context.project_id = "admin-project"
    router = SimpleNamespace(id="r1", project_id="project-1", gw_port=None)
    router_dict = {"id": router.id, "flavor_id": "f1"}
    interface_port = {
        **_INTERFACE_PORT,
        "network_id": "tenant-net",
        "project_id": router.project_id,
        "fixed_ips": [{"subnet_id": "subnet-1", "ip_address": "10.0.0.1"}],
    }
    subnet = {"id": "subnet-1", "cidr": "10.0.0.0/24"}

    def create_port(_context, body):
        port = copy.deepcopy(body["port"])
        is_parent = port.get("name", "").startswith("palo-alto-router-anchor-")
        port["id"] = "parent-1" if is_parent else "intf-1"
        state.ports[port["id"]] = port
        if is_parent:
            fail_at("parent_create")
        return copy.deepcopy(port)

    def update_port(_context, port_id, body):
        state.ports[port_id].update(body["port"])
        return copy.deepcopy(state.ports[port_id])

    def delete_port(ctx, port_id, l3_port_check=True):
        registry.publish(
            resources.PORT,
            events.BEFORE_DELETE,
            core,
            payload=events.DBEventPayload(
                ctx,
                resource_id=port_id,
                metadata={
                    "port": copy.deepcopy(state.ports[port_id]),
                    "port_check": l3_port_check,
                },
            ),
        )
        del state.ports[port_id]
        state.associations.discard(port_id)

    core.create_port.side_effect = create_port
    core.update_port.side_effect = update_port
    core.delete_port.side_effect = delete_port
    core.get_port.side_effect = lambda _ctx, port_id: copy.deepcopy(
        state.ports[port_id]
    )
    core.get_ports.side_effect = lambda _ctx, filters: [
        copy.deepcopy(port)
        for port in state.ports.values()
        if all(port.get(key) in values for key, values in filters.items())
    ]
    core.get_networks.return_value = [{"id": "anchor-net"}]

    def create_trunk(_context, body):
        trunk = {"id": "trunk-1", **copy.deepcopy(body["trunk"])}
        state.trunks[trunk["id"]] = trunk
        fail_at("trunk_create")
        return copy.deepcopy(trunk)

    def add_subports(_context, trunk_id, body):
        fail_at("subport_precommit")
        state.trunks[trunk_id]["sub_ports"].extend(copy.deepcopy(body["sub_ports"]))
        fail_at("subport_postcommit")
        return copy.deepcopy(state.trunks[trunk_id])

    def remove_subports(_context, trunk_id, body):
        removed = {sp["port_id"] for sp in body["sub_ports"]}
        state.trunks[trunk_id]["sub_ports"] = [
            sp
            for sp in state.trunks[trunk_id]["sub_ports"]
            if sp["port_id"] not in removed
        ]
        return copy.deepcopy(state.trunks[trunk_id])

    trunk_plugin.create_trunk.side_effect = create_trunk
    trunk_plugin.add_subports.side_effect = add_subports
    trunk_plugin.remove_subports.side_effect = remove_subports
    trunk_plugin.get_trunks.side_effect = lambda _ctx, filters: [
        copy.deepcopy(trunk)
        for trunk in state.trunks.values()
        if trunk["name"] in filters["name"]
    ]
    trunk_plugin.get_trunk.side_effect = lambda _ctx, tid: copy.deepcopy(
        state.trunks[tid]
    )
    trunk_plugin.delete_trunk.side_effect = lambda _ctx, tid: state.trunks.pop(tid)
    mocker.patch.object(
        palo_alto.utils, "fetch_trunk_plugin", return_value=trunk_plugin
    )
    mocker.patch.object(
        palo_alto.utils,
        "allowed_tenant_vlan_id_ranges",
        side_effect=lambda: (
            [(200, 200)] if state.fail == "vlan_allocation" else [(200, 210)]
        ),
    )
    mocker.patch.object(
        palo_alto.utils,
        "clear_device_id_for_port",
        side_effect=lambda pid: update_port(context, pid, {"port": {"device_id": ""}}),
    )
    mocker.patch.object(
        palo_alto.utils,
        "set_device_id_and_owner_for_port",
        side_effect=lambda pid, did, owner: update_port(
            context, pid, {"port": {"device_id": did, "device_owner": owner}}
        ),
    )

    def attach_vif(_node, port_id):
        fail_at("vif_attach")
        state.vifs.add(port_id)
        fail_at("vif_annotation")
        state.ports[port_id].update(
            {
                "binding:host_id": "node-1",
                "binding:profile": {
                    "physical_network": "physnet-1",
                    "local_link_information": [
                        {"switch_info": "switch-1", "port_id": "Eth1"}
                    ],
                },
            }
        )

    ironic.node_by_instance_uuid.return_value = SimpleNamespace(id="node-1")
    ironic.node_vif_ids.side_effect = lambda _node: list(state.vifs)
    ironic.attach_vif_to_node.side_effect = attach_vif
    ironic.detach_vif_from_node.side_effect = lambda _node, pid: state.vifs.discard(pid)
    provider = _make_provider(
        mocker, FakeFlavorPlugin(_palo_alto_driver()), ironic=ironic, core_plugin=core
    )
    palo_alto.n_context.get_admin_context.return_value = context

    # Bind the installed Neutron methods, including its real rollback context
    # managers. Only persistence and pre-event subnet validation are doubled.
    l3 = SimpleNamespace(
        _core_plugin=core,
        _get_router=mocker.Mock(return_value=router),
        get_router=mocker.Mock(return_value=router_dict),
        _get_device_owner=mocker.Mock(return_value=const.DEVICE_OWNER_ROUTER_INTF),
        _validate_interface_info=mocker.Mock(
            side_effect=lambda info: ("port_id" in info, "subnet_id" in info)
        ),
        _check_router_port=mocker.Mock(
            side_effect=lambda _ctx, pid, _owner: copy.deepcopy(state.ports[pid])
        ),
        _validate_router_port_info=mocker.Mock(
            side_effect=lambda _ctx, _router, pid: (
                copy.deepcopy(state.ports[pid]),
                [subnet],
            )
        ),
        _add_interface_by_subnet=mocker.Mock(
            side_effect=lambda _ctx, _router, _sid, _owner: (
                create_port(context, {"port": interface_port}),
                [subnet],
                True,
            )
        ),
        router_device_owners=l3_db.L3_NAT_dbonly_mixin.router_device_owners,
    )
    for method in (
        "add_router_interface",
        "_notify_attaching_interface",
        "_add_interface_by_port",
        "_add_router_port",
        "prevent_l3_port_deletion",
    ):
        setattr(l3, method, MethodType(getattr(l3_db.L3_NAT_dbonly_mixin, method), l3))
    l3._make_router_interface_info = (
        l3_db.L3_NAT_dbonly_mixin._make_router_interface_info
    )
    router_port = mocker.patch.object(l3_db.l3_obj, "RouterPort")
    router_port.return_value.create.side_effect = lambda: state.associations.add(
        "intf-1"
    )
    router_port.get_objects.return_value = []
    router_port.objects_exist.side_effect = lambda _ctx, router_id, port_id: (
        port_id in state.associations
    )
    mocker.patch.object(l3_db.l3_obj.Router, "objects_exist", return_value=True)
    provider.l3plugin = l3
    mocker.patch.object(
        palo_alto.directory,
        "get_plugin",
        side_effect=lambda plugin=None: (
            l3 if plugin == palo_alto.plugin_constants.L3 else core
        ),
    )
    registry.subscribe(
        l3_db.L3_NAT_dbonly_mixin._prevent_l3_port_delete_callback,
        resources.PORT,
        events.BEFORE_DELETE,
    )
    registry.subscribe(
        trunk_rules.enforce_port_deletion_rules, resources.PORT, events.BEFORE_DELETE
    )
    mocker.patch.object(
        trunk_rules.trunk_objects.SubPort,
        "get_object",
        side_effect=lambda _ctx, port_id: next(
            (
                SimpleNamespace(trunk_id=trunk["id"])
                for trunk in state.trunks.values()
                for sp in trunk["sub_ports"]
                if sp["port_id"] == port_id
            ),
            None,
        ),
    )
    mocker.patch.object(
        trunk_rules.trunk_objects.Trunk, "get_object", return_value=None
    )
    return SimpleNamespace(
        state=state,
        provider=provider,
        core=core,
        trunk_plugin=trunk_plugin,
        ironic=ironic,
        context=context,
        l3=l3,
        router_port=router_port,
        interface_port=interface_port,
        router=router_dict,
    )


class TestRouterInterfaceLifecycle:
    def _add(self, env, by_port=False):
        info = {"port_id": "intf-1"} if by_port else {"subnet_id": "subnet-1"}
        return env.l3.add_router_interface(env.context, "r1", info)

    def test_rejected_direct_delete_preserves_live_subport(self, interface_lifecycle):
        env = interface_lifecycle
        self._add(env)
        before = copy.deepcopy(env.state)

        with pytest.raises(callback_exc.CallbackFailure) as error:
            env.core.delete_port(env.context, "intf-1")

        assert any(
            isinstance(exc, n_exc.ServicePortInUse)
            for exc in error.value.inner_exceptions
        )
        assert env.state == before
        env.trunk_plugin.remove_subports.assert_not_called()
        env.ironic.detach_vif_from_node.assert_not_called()

    def test_authorized_delete_unwires_before_trunk_guard(self, interface_lifecycle):
        env = interface_lifecycle
        self._add(env)

        env.core.delete_port(env.context, "intf-1", l3_port_check=False)

        assert not env.state.ports
        assert not env.state.trunks
        assert not env.state.vifs
        assert not env.state.associations

    @pytest.mark.parametrize("by_port", [False, True], ids=["by-subnet", "by-port"])
    @pytest.mark.parametrize(
        "stage",
        [
            "parent_create",
            "vif_attach",
            "vif_annotation",
            "trunk_create",
            "vlan_allocation",
            "subport_precommit",
            "subport_postcommit",
        ],
    )
    def test_attach_failure_unwinds_and_allows_retry(
        self, interface_lifecycle, by_port, stage
    ):
        env = interface_lifecycle
        original = {**env.interface_port, "device_id": "", "device_owner": ""}
        if by_port:
            env.state.ports["intf-1"] = copy.deepcopy(original)
        env.state.fail = stage

        with pytest.raises(l3_exc.RouterInterfaceAttachmentConflict):
            self._add(env, by_port)

        env.router_port.assert_not_called()
        assert not env.state.associations
        assert not env.state.trunks
        assert not env.state.vifs
        assert env.state.ports == ({"intf-1": original} if by_port else {})
        if by_port:
            assert all(
                call.args[1] != "intf-1" for call in env.core.delete_port.call_args_list
            )

        env.state.fail = None
        self._add(env, by_port)
        assert env.state.associations == {"intf-1"}
        assert env.state.trunks["trunk-1"]["sub_ports"] == [
            {"port_id": "intf-1", "segmentation_type": "vlan", "segmentation_id": 201}
        ]

    @pytest.mark.parametrize(
        "priority",
        [
            priority_group.PRIORITY_DEFAULT,
            priority_group.PRIORITY_ROUTER_DRIVER + 1,
        ],
        ids=["earlier-validator", "later-validator"],
    )
    def test_other_callback_rejection_unwinds_successful_attach(
        self, interface_lifecycle, mocker, priority
    ):
        env = interface_lifecycle
        env.state.ports["intf-1"] = {
            **env.interface_port,
            "device_id": "",
            "device_owner": "",
        }
        reject = mocker.Mock(
            side_effect=n_exc.BadRequest(resource="router", msg="validation failed")
        )
        registry.subscribe(
            reject, resources.ROUTER_INTERFACE, events.BEFORE_CREATE, priority=priority
        )

        with pytest.raises(l3_exc.RouterInterfaceAttachmentConflict):
            self._add(env, by_port=True)

        env.router_port.assert_not_called()
        assert not env.state.trunks
        assert not env.state.vifs
        assert set(env.state.ports) == {"intf-1"}
        assert env.state.ports["intf-1"]["device_id"] == ""

    @pytest.mark.parametrize("existing_trunk", [False, True])
    @pytest.mark.parametrize("existing_vif", [False, True])
    def test_failure_preserves_preexisting_empty_stack(
        self, interface_lifecycle, existing_trunk, existing_vif
    ):
        env = interface_lifecycle
        parent = env.provider._ensure_parent_port(env.router)
        if existing_vif:
            env.provider._ensure_parent_vif_attached(env.router, parent)
        if existing_trunk:
            env.provider._ensure_trunk(env.router, parent)
        trunks = copy.deepcopy(env.state.trunks)
        vifs = set(env.state.vifs)
        env.state.fail = "subport_postcommit"

        with pytest.raises(l3_exc.RouterInterfaceAttachmentConflict):
            self._add(env)

        assert env.state.trunks == trunks
        assert env.state.vifs == vifs
        assert set(env.state.ports) == {"parent-1"}
        assert not env.state.associations

    def test_failed_subnet_preserves_existing_gateway(self, interface_lifecycle):
        env = interface_lifecycle
        parent = env.provider._ensure_parent_port(env.router)
        env.provider._ensure_parent_vif_attached(env.router, parent)
        env.provider._ensure_trunk(env.router, parent)
        env.state.trunks["trunk-1"]["sub_ports"] = [
            {"port_id": "gw-1", "segmentation_type": "vlan", "segmentation_id": 200}
        ]
        before = copy.deepcopy(env.state)
        env.state.fail = "subport_postcommit"

        with pytest.raises(l3_exc.RouterInterfaceAttachmentConflict):
            self._add(env)

        assert env.state.ports == before.ports
        assert env.state.trunks == before.trunks
        assert env.state.vifs == before.vifs
        env.ironic.detach_vif_from_node.assert_not_called()

    def test_abort_retries_failed_compensation(
        self, interface_lifecycle, mocker, caplog
    ):
        env = interface_lifecycle
        env.state.fail = "subport_postcommit"
        cleanup = env.provider._remove_interface_subport
        attempts = []

        def fail_once(*args):
            attempts.append(args)
            if len(attempts) == 1:
                raise RuntimeError("transient cleanup failure")
            return cleanup(*args)

        mocker.patch.object(
            env.provider, "_remove_interface_subport", side_effect=fail_once
        )
        with pytest.raises(
            l3_exc.RouterInterfaceAttachmentConflict, match="subport_postcommit"
        ):
            self._add(env)

        assert len(attempts) == 2
        assert "attachment cleanup is incomplete" in caplog.text
        assert not env.state.trunks
        assert not env.state.vifs
        assert not env.state.ports
        assert not env.state.associations
