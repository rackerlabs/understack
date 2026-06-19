from neutron_lib import constants as const

from neutron_understack.l3_router import svi


class FakeFlavorPlugin:
    def __init__(self, driver):
        self.driver = driver

    def get_flavor(self, _context, flavor_id):
        return {"id": flavor_id}

    def get_flavor_next_provider(self, _context, _flavor_id):
        return [{"driver": self.driver}]


def _svi_driver():
    return f"{svi.Svi.__module__}.{svi.Svi.__name__}"


class TestSviProvider:
    def test_flavor_plugin_is_cached(self, mocker):
        plugin = FakeFlavorPlugin(_svi_driver())
        get_plugin = mocker.patch.object(
            svi.directory, "get_plugin", return_value=plugin
        )
        provider = svi.Svi(None)

        assert provider._flavor_plugin is plugin
        assert provider._flavor_plugin is plugin
        get_plugin.assert_called_once_with(svi.plugin_constants.FLAVORS)

    def test_is_svi_flavor_returns_false_without_flavor(self, mocker):
        get_plugin = mocker.patch.object(svi.directory, "get_plugin")
        provider = svi.Svi(None)

        assert provider._is_svi_flavor("context", {"id": "router-a"}) is False
        assert (
            provider._is_svi_flavor(
                "context",
                {"id": "router-a", "flavor_id": const.ATTR_NOT_SPECIFIED},
            )
            is False
        )
        get_plugin.assert_not_called()

    def test_is_svi_flavor_returns_true_for_svi_driver(self, mocker):
        plugin = FakeFlavorPlugin(_svi_driver())
        mocker.patch.object(svi.directory, "get_plugin", return_value=plugin)
        provider = svi.Svi(None)

        assert (
            provider._is_svi_flavor(
                "context",
                {"id": "router-a", "flavor_id": "svi-flavor-id"},
            )
            is True
        )

    def test_is_svi_flavor_returns_false_for_different_driver(self, mocker):
        plugin = FakeFlavorPlugin("neutron_understack.l3_router.vrf.Vrf")
        mocker.patch.object(svi.directory, "get_plugin", return_value=plugin)
        provider = svi.Svi(None)

        assert (
            provider._is_svi_flavor(
                "context",
                {"id": "router-a", "flavor_id": "vrf-flavor-id"},
            )
            is False
        )
