"""Scenario tests for the Palo Alto router flavor (Ironic netdev adoption).

See neutron_understack/tests/scenarios/SCENARIOS.md (PALO-*) for the catalog.
"""

import json
from unittest import mock

import pytest
from neutron_lib.plugins import constants as plugin_constants
from neutron_lib.plugins import directory
from oslo_config import cfg

from neutron_understack.tests.scenarios.base import UnderstackMl2RouterScenarioBase
from neutron_understack.tests.scenarios.fakes import FakeIronicClient

PALO_DRIVER = "neutron_understack.l3_router.palo_alto.PaloAlto"


class TestPaloAltoRouter(UnderstackMl2RouterScenarioBase):
    def setUp(self):
        # Register the Palo Alto provider so its ROUTER callbacks are wired.
        cfg.CONF.set_override(
            "service_provider",
            [f"L3_ROUTER_NAT:palo_alto:{PALO_DRIVER}:default"],
            group="service_providers",
        )
        super().setUp()
        self.flavor_plugin = directory.get_plugin(plugin_constants.FLAVORS)

    def _palo_flavor(self, resource_class="netdev-fw"):
        profile = self.flavor_plugin.create_service_profile(
            self.context,
            {
                "service_profile": {
                    "driver": PALO_DRIVER,
                    "metainfo": json.dumps({"resource_class": resource_class}),
                    "enabled": True,
                    "description": "palo alto",
                }
            },
        )
        flavor = self.flavor_plugin.create_flavor(
            self.context,
            {
                "flavor": {
                    "name": "palo-alto",
                    "service_type": plugin_constants.L3,
                    "enabled": True,
                    "description": "palo alto flavor",
                }
            },
        )
        self.flavor_plugin.create_flavor_service_profile(
            self.context,
            {"service_profile": {"id": profile["id"]}},
            flavor["id"],
        )
        return flavor["id"]

    @pytest.mark.scenario("PALO-ROUTER-ADOPT-01")
    def test_palo_alto_router_adopts_ironic_node(self):
        fake_ironic = FakeIronicClient()
        flavor_id = self._palo_flavor()

        with mock.patch(
            "neutron_understack.l3_router.palo_alto.IronicClient",
            return_value=fake_ironic,
        ):
            router = self.l3_plugin.create_router(
                self.context,
                {
                    "router": {
                        "name": "pa-router",
                        "admin_state_up": True,
                        "project_id": self._project_id,
                        "flavor_id": flavor_id,
                    }
                },
            )

        # The router adopted the single available netdev node.
        assert len(fake_ironic.adopted) == 1, fake_ironic.adopted
        assert fake_ironic.adopted[0]["router_id"] == router["id"]

    @pytest.mark.scenario("PALO-ROUTER-RELEASE-01")
    def test_palo_alto_router_delete_releases_ironic_node(self):
        fake_ironic = FakeIronicClient()
        flavor_id = self._palo_flavor()

        with mock.patch(
            "neutron_understack.l3_router.palo_alto.IronicClient",
            return_value=fake_ironic,
        ):
            router = self.l3_plugin.create_router(
                self.context,
                {
                    "router": {
                        "name": "pa-router",
                        "admin_state_up": True,
                        "project_id": self._project_id,
                        "flavor_id": flavor_id,
                    }
                },
            )
            self.l3_plugin.delete_router(self.context, router["id"])

        # The adopted node was returned to the pool on delete.
        assert fake_ironic.released == [router["id"]], fake_ironic.released
