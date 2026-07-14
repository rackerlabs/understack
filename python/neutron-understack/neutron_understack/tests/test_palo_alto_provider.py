from neutron_lib import constants as const

from neutron_understack.l3_router import palo_alto


class FakeFlavorPlugin:
    def __init__(self, driver):
        self.driver = driver

    def get_flavor(self, _context, flavor_id):
        return {"id": flavor_id}

    def get_flavor_next_provider(self, _context, _flavor_id):
        return [{"driver": self.driver}]


class FakePayload:
    def __init__(self, router, context="context"):
        self.states = (router,)
        self.context = context
        self.resource_id = router.get("id")


def _palo_alto_driver():
    return f"{palo_alto.PaloAlto.__module__}.{palo_alto.PaloAlto.__name__}"


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

    def test_router_create_is_noop_for_palo_alto_router(self, mocker):
        plugin = FakeFlavorPlugin(_palo_alto_driver())
        mocker.patch.object(palo_alto.directory, "get_plugin", return_value=plugin)
        l3_plugin = mocker.Mock()
        provider = palo_alto.PaloAlto(l3_plugin)
        payload = FakePayload({"id": "router-a", "flavor_id": "palo-alto-flavor-id"})

        result = provider._process_router_create(
            "router", "after_create", "trigger", payload
        )

        # Stub flavor: no action is taken on a matching router.
        assert result is None
        assert l3_plugin.mock_calls == []

    def test_router_create_skips_non_palo_alto_router(self, mocker):
        plugin = FakeFlavorPlugin("neutron_understack.l3_router.vrf.Vrf")
        mocker.patch.object(palo_alto.directory, "get_plugin", return_value=plugin)
        l3_plugin = mocker.Mock()
        provider = palo_alto.PaloAlto(l3_plugin)
        payload = FakePayload({"id": "router-b", "flavor_id": "vrf-flavor-id"})

        result = provider._process_router_create(
            "router", "after_create", "trigger", payload
        )

        assert result is None
        assert l3_plugin.mock_calls == []
