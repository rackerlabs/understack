import pytest
from neutron_lib import constants as const

from neutron_understack.l3_router import palo_alto


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
