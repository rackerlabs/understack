"""In-process ML2 scenario-test harness for the understack mechanism drivers.

These tests reuse neutron's own functional test bases, which stand up a real
``Ml2Plugin`` backed by in-memory SQLite. We load our two mechanism drivers --
``understack`` and ``undersync`` -- into the binding chain and drive real
``create_network`` / ``create_port`` / router operations through the ML2 manager,
so a scenario can assert *which* calls reach our drivers and *with what data*.
This is the same style upstream neutron uses to test its own ML2 drivers.

``UnderstackMl2ScenarioBase`` is the plain base (port binding scenarios).
``UnderstackMl2RouterScenarioBase`` adds a real L3 router + flavors plugin
(``ML2TestFramework``) for router scenarios.

Only the genuine external edge on the binding path -- the Undersync HTTP client --
is mocked. Router scenarios that reach the OVN uplink path would additionally
need the OVN IDL faked; the flavored (VRF) router path skips it.
"""

from unittest import mock

from neutron.conf.plugins.ml2.drivers import driver_type
from neutron.tests.unit.plugins.ml2.base import ML2TestFramework
from neutron.tests.unit.plugins.ml2.test_plugin import Ml2PluginV2TestCase
from neutron_lib.api.definitions import portbindings
from neutron_lib.plugins import directory
from oslo_config import cfg

from neutron_understack import config as understack_config
from neutron_understack.undersync import Undersync

#: Physnets the type manager knows about (the parent setUp configures physnet1/2
#: with VLAN ranges), so ``allocate_dynamic_segment`` succeeds for the VLAN group
#: named in a baremetal binding profile.
DEFAULT_PHYSNET = "physnet1"
SECOND_PHYSNET = "physnet2"

#: Stand-in switch identity for the binding profile's local_link_information.
DEFAULT_SWITCH_ID = "11:22:33:44:55:66"
DEFAULT_SWITCH_INFO = "a1-1-1.iad3.rackspace.net"


def _apply_understack_ml2_overrides():
    """Config overrides the plugin needs before it loads in setup_parent().

    Tenant networks are VXLAN (matching production); dynamic VLAN segments come
    from the physnet ranges the parent setUp configures.
    """
    cfg.CONF.set_override("project_network_types", ["vxlan"], group="ml2")
    # ml2_type_vxlan is only registered when the vxlan type driver loads, so
    # register it here before overriding its (empty) vni_ranges.
    driver_type.register_ml2_drivers_vxlan_opts(cfg.CONF)
    cfg.CONF.set_override("vni_ranges", ["1000:2000"], group="ml2_type_vxlan")

    # UnderstackDriver.initialize() registers these itself, but we register up
    # front so we can set values the driver reads while loading.
    understack_config.register_ml2_understack_opts(cfg.CONF)
    cfg.CONF.set_override(
        "undersync_url", "http://undersync.test", group="ml2_understack"
    )
    cfg.CONF.set_override("undersync_dry_run", False, group="ml2_understack")
    cfg.CONF.set_override(
        "provisioning_network",
        "00000000-0000-0000-0000-000000000000",
        group="ml2_understack",
    )


class _UnderstackMl2ScenarioMixin:
    """Shared setUp + helpers for understack ML2 scenario bases."""

    # Order matters: understack does hierarchical VXLAN->VLAN binding and
    # undersync finalizes the VLAN segment. 'logger' mirrors the production list.
    _mechanism_drivers = ["logger", "understack", "undersync"]

    def setUp(self):
        _apply_understack_ml2_overrides()
        super().setUp()
        # Replace the real HTTP Undersync client with a mock -- the single
        # genuine external edge on the binding path. The trunk driver captured
        # its own reference at construction (trunk.py), so patch that too.
        self.understack_driver = self._mech_driver("understack")
        self.undersync_mock = mock.MagicMock(spec_set=Undersync)
        self.understack_driver.undersync = self.undersync_mock
        self.understack_driver.trunk_driver.undersync = self.undersync_mock

    @staticmethod
    def _mech_driver(name):
        """Return the loaded mechanism driver instance registered under ``name``."""
        manager = directory.get_plugin().mechanism_manager
        for ext in manager.ordered_mech_drivers:
            if ext.name == name:
                return ext.obj
        raise AssertionError(f"mechanism driver {name!r} not loaded")

    @staticmethod
    def baremetal_binding_profile(physnet=DEFAULT_PHYSNET, port_id="Ethernet1/1"):
        """A baremetal port binding profile as Ironic supplies on vif-attach.

        ``physical_network`` names the VLAN group; ``local_link_information``
        identifies the switch port. Pass ``physnet=None`` to omit the
        ``physical_network`` key (the "missing physnet" edge case).
        """
        profile: dict = {
            "local_link_information": [
                {
                    "port_id": port_id,
                    "switch_id": DEFAULT_SWITCH_ID,
                    "switch_info": DEFAULT_SWITCH_INFO,
                }
            ],
        }
        if physnet is not None:
            profile["physical_network"] = physnet
        return profile


class UnderstackMl2ScenarioBase(_UnderstackMl2ScenarioMixin, Ml2PluginV2TestCase):
    """Base for port-binding scenarios (no L3/router machinery)."""


class UnderstackMl2RouterScenarioBase(_UnderstackMl2ScenarioMixin, ML2TestFramework):
    """Base for router scenarios: real L3RouterPlugin + flavors plugin.

    ``self.l3_plugin`` is the loaded L3 plugin and ``self._create_router()``
    creates a router directly (bypassing HTTP), both provided by ML2TestFramework.
    """

    def _bind_baremetal_port(self, net_id, physnet, host):
        """Create a baremetal port on the network and vif-attach it to physnet."""
        res = self._create_port(
            self.fmt,
            net_id,
            arg_list=(portbindings.VNIC_TYPE,),
            is_admin=True,
            **{portbindings.VNIC_TYPE: portbindings.VNIC_BAREMETAL},
        )
        assert res.status_int == 201, res.body
        port_id = self.deserialize(self.fmt, res)["port"]["id"]
        data = {
            "port": {
                portbindings.HOST_ID: host,
                portbindings.PROFILE: self.baremetal_binding_profile(physnet=physnet),
            }
        }
        req = self.new_update_request("ports", data, port_id, as_service=True)
        assert req.get_response(self.api).status_int == 200
        return port_id
