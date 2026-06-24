import logging
from types import SimpleNamespace

import pytest
from neutron_lib import constants as const
from neutron_lib import exceptions as n_exc

from neutron_understack.l3_router import svi


class FakeCorePlugin:
    def __init__(self, subnets, subnetpools=None, ports=None):
        self.subnets = subnets
        self.subnetpools = subnetpools or {}
        self.ports = ports or []

    def get_subnet(self, _context, subnet_id):
        return self.subnets[subnet_id]

    def get_subnetpool(self, _context, subnetpool_id):
        return self.subnetpools[subnetpool_id]

    def get_ports(self, _context, filters=None):
        return self.ports


class FakeFlavorPlugin:
    def __init__(self, driver):
        self.driver = driver

    def get_flavor(self, _context, flavor_id):
        return {"id": flavor_id}

    def get_flavor_next_provider(self, _context, _flavor_id):
        return [{"driver": self.driver}]


class FakeL3Plugin:
    def __init__(self, router):
        self.router = router

    def get_router(self, _context, _router_id):
        return self.router


def _subnet(subnetpool_id, ip_version=4):
    return {"ip_version": ip_version, "subnetpool_id": subnetpool_id}


def _subnetpool(scope_id):
    return {"address_scope_id": scope_id}


def _patch_core_plugin(mocker, plugin):
    mocker.patch.object(svi.directory, "get_plugin", return_value=plugin)


def _patch_plugins(mocker, *, core_plugin, l3_plugin, flavor_plugin):
    def get_plugin(plugin_type=None):
        if plugin_type == svi.plugin_constants.L3:
            return l3_plugin
        if plugin_type == svi.plugin_constants.FLAVORS:
            return flavor_plugin
        return core_plugin

    mocker.patch.object(svi.directory, "get_plugin", side_effect=get_plugin)


def _svi_driver():
    return f"{svi.Svi.__module__}.{svi.Svi.__name__}"


class TestValidateAddressScopeRules:
    def test_rejects_new_subnet_without_scope(self, mocker):
        plugin = FakeCorePlugin({"subnet-a": _subnet(None)})
        _patch_core_plugin(mocker, plugin)

        with pytest.raises(n_exc.BadRequest) as exc_info:
            svi._validate_address_scope_rules("context", "router-a", ["subnet-a"])

        assert "must belong to an address scope" in str(exc_info.value)

    def test_rejects_new_subnet_with_subnetpool_without_scope(self, mocker):
        plugin = FakeCorePlugin(
            {"subnet-a": _subnet("pool-a")},
            {"pool-a": _subnetpool(None)},
        )
        _patch_core_plugin(mocker, plugin)

        with pytest.raises(n_exc.BadRequest) as exc_info:
            svi._validate_address_scope_rules("context", "router-a", ["subnet-a"])

        assert "must belong to an address scope" in str(exc_info.value)

    def test_accepts_new_subnets_with_same_scope(self, mocker):
        plugin = FakeCorePlugin(
            {
                "subnet-a": _subnet("pool-a"),
                "subnet-b": _subnet("pool-b"),
            },
            {
                "pool-a": _subnetpool("scope-a"),
                "pool-b": _subnetpool("scope-a"),
            },
        )
        _patch_core_plugin(mocker, plugin)

        scopes = svi._validate_address_scope_rules(
            "context", "router-a", ["subnet-a", "subnet-b"]
        )

        assert scopes == {4: "scope-a"}

    def test_rejects_new_ipv6_subnet(self, mocker):
        plugin = FakeCorePlugin(
            {"subnet-v6": _subnet("pool-v6", ip_version=6)},
            {"pool-v6": _subnetpool("scope-v6")},
        )
        _patch_core_plugin(mocker, plugin)

        with pytest.raises(n_exc.BadRequest) as exc_info:
            svi._validate_address_scope_rules("context", "router-a", ["subnet-v6"])

        assert "IPv6 subnet subnet-v6 cannot be attached" in str(exc_info.value)

    def test_rejects_new_subnets_with_different_scopes(self, mocker):
        plugin = FakeCorePlugin(
            {
                "subnet-a": _subnet("pool-a"),
                "subnet-b": _subnet("pool-b"),
            },
            {
                "pool-a": _subnetpool("scope-a"),
                "pool-b": _subnetpool("scope-b"),
            },
        )
        _patch_core_plugin(mocker, plugin)

        with pytest.raises(n_exc.BadRequest) as exc_info:
            svi._validate_address_scope_rules(
                "context", "router-a", ["subnet-a", "subnet-b"]
            )

        assert "same request" in str(exc_info.value)

    def test_rejects_conflict_with_existing_router_subnet(self, mocker):
        plugin = FakeCorePlugin(
            {
                "new-subnet": _subnet("new-pool"),
                "existing-subnet": _subnet("existing-pool"),
            },
            {
                "new-pool": _subnetpool("new-scope"),
                "existing-pool": _subnetpool("existing-scope"),
            },
            ports=[{"fixed_ips": [{"subnet_id": "existing-subnet"}]}],
        )
        _patch_core_plugin(mocker, plugin)

        with pytest.raises(n_exc.BadRequest) as exc_info:
            svi._validate_address_scope_rules("context", "router-a", ["new-subnet"])

        assert "differs from scope" in str(exc_info.value)

    def test_rejects_existing_router_subnet_without_scope(self, mocker):
        plugin = FakeCorePlugin(
            {
                "new-subnet": _subnet("new-pool"),
                "existing-subnet": _subnet(None),
            },
            {"new-pool": _subnetpool("scope-a")},
            ports=[{"fixed_ips": [{"subnet_id": "existing-subnet"}]}],
        )
        _patch_core_plugin(mocker, plugin)

        with pytest.raises(n_exc.BadRequest) as exc_info:
            svi._validate_address_scope_rules("context", "router-a", ["new-subnet"])

        assert "must belong to an address scope" in str(exc_info.value)


class TestValidateSviRouterPort:
    def test_skips_non_internal_router_interface(self):
        checked = svi.validate_svi_router_port(
            "context",
            {
                "id": "port-a",
                "device_owner": const.DEVICE_OWNER_ROUTER_GW,
                "device_id": "router-a",
            },
        )

        assert checked is False

    def test_skips_non_svi_router_interface(self, mocker):
        core_plugin = FakeCorePlugin({"subnet-a": _subnet(None)})
        l3_plugin = FakeL3Plugin(
            {"id": "router-a", "name": "vrf-router", "flavor_id": "flavor-a"}
        )
        flavor_plugin = FakeFlavorPlugin("neutron_understack.l3_router.vrf.Vrf")
        _patch_plugins(
            mocker,
            core_plugin=core_plugin,
            l3_plugin=l3_plugin,
            flavor_plugin=flavor_plugin,
        )

        checked = svi.validate_svi_router_port(
            "context",
            {
                "id": "port-a",
                "device_owner": const.DEVICE_OWNER_ROUTER_INTF,
                "device_id": "router-a",
                "fixed_ips": [{"subnet_id": "subnet-a"}],
            },
        )

        assert checked is False

    def test_rejects_svi_router_interface_without_scope(self, mocker):
        core_plugin = FakeCorePlugin({"subnet-a": _subnet(None)})
        l3_plugin = FakeL3Plugin(
            {"id": "router-a", "name": "svi-router", "flavor_id": "flavor-a"}
        )
        flavor_plugin = FakeFlavorPlugin(_svi_driver())
        _patch_plugins(
            mocker,
            core_plugin=core_plugin,
            l3_plugin=l3_plugin,
            flavor_plugin=flavor_plugin,
        )

        with pytest.raises(n_exc.BadRequest) as exc_info:
            svi.validate_svi_router_port(
                "context",
                {
                    "id": "port-a",
                    "device_owner": const.DEVICE_OWNER_ROUTER_INTF,
                    "device_id": "router-a",
                    "fixed_ips": [{"subnet_id": "subnet-a"}],
                },
            )

        assert "must belong to an address scope" in str(exc_info.value)


class TestValidateSviRouterInterfaceCallback:
    def test_rejects_svi_router_interface_without_scope(self, caplog, mocker):
        core_plugin = FakeCorePlugin({"subnet-a": _subnet(None)})
        flavor_plugin = FakeFlavorPlugin(_svi_driver())
        _patch_plugins(
            mocker,
            core_plugin=core_plugin,
            l3_plugin=FakeL3Plugin({}),
            flavor_plugin=flavor_plugin,
        )

        payload = SimpleNamespace(
            context="context",
            resource_id="router-a",
            states=(
                {
                    "id": "router-a",
                    "name": "svi-router",
                    "flavor_id": "flavor-a",
                },
            ),
            metadata={
                "port": {
                    "id": "port-a",
                    "network_id": "network-a",
                    "device_owner": const.DEVICE_OWNER_ROUTER_INTF,
                    "fixed_ips": [{"subnet_id": "subnet-a"}],
                },
                "interface_info": {"port_id": "port-a"},
            },
        )
        provider = svi.Svi(None)

        caplog.set_level(logging.INFO, logger=svi.LOG.name)
        with pytest.raises(n_exc.BadRequest) as exc_info:
            provider._validate_svi_router_interface(None, None, None, payload)

        assert "must belong to an address scope" in str(exc_info.value)
        assert "attach_mode=port" in caplog.text
