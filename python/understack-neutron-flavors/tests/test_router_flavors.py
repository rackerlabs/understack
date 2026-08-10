import json
import sys
import unittest
from pathlib import Path

from understack_neutron_flavors import create_router_flavors
from understack_neutron_flavors import delete_router_flavors
from understack_neutron_flavors import router_flavors
from understack_neutron_flavors import router_flavors_common as common
from understack_neutron_flavors import update_router_flavors

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))


class NotFound(Exception):
    status_code = 404


class Conflict(Exception):
    status_code = 409


class FakeNetwork:
    def __init__(self, flavors, profiles, routers=None):
        self._flavors = {flavor["id"]: dict(flavor) for flavor in flavors}
        self._profiles = {profile["id"]: dict(profile) for profile in profiles}
        self._routers = [dict(router) for router in routers or []]
        self.deleted_flavors = []
        self.deleted_profiles = []
        self.created_flavors = []
        self.created_profiles = []
        self.updated_flavors = []

    def flavors(self, **query):
        flavors = list(self._flavors.values())
        if "service_type" in query:
            flavors = [
                flavor
                for flavor in flavors
                if flavor.get("service_type") == query["service_type"]
            ]
        if "name" in query:
            flavors = [
                flavor for flavor in flavors if flavor.get("name") == query["name"]
            ]
        return iter(flavors)

    def get_service_profile(self, profile_id):
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise NotFound(profile_id) from exc

    def service_profiles(self):
        return iter(self._profiles.values())

    def create_service_profile(self, **attrs):
        profile_id = f"sp-created-{len(self._profiles) + 1}"
        profile = {"id": profile_id, **attrs}
        self._profiles[profile_id] = profile
        self.created_profiles.append(profile)
        return profile

    def get_flavor(self, flavor):
        flavor_id = flavor["id"] if isinstance(flavor, dict) else flavor
        try:
            return self._flavors[flavor_id]
        except KeyError as exc:
            raise NotFound(flavor_id) from exc

    def create_flavor(self, **attrs):
        flavor_id = f"fl-created-{len(self._flavors) + 1}"
        flavor = {"id": flavor_id, **attrs}
        self._flavors[flavor_id] = flavor
        self.created_flavors.append(flavor)
        return flavor

    def update_flavor(self, flavor, **attrs):
        flavor_id = flavor["id"] if isinstance(flavor, dict) else flavor
        current = self.get_flavor(flavor_id)
        current.update(attrs)
        self.updated_flavors.append({"id": flavor_id, **attrs})
        return current

    def delete_flavor(self, flavor, ignore_missing=True):
        flavor_id = flavor["id"] if isinstance(flavor, dict) else flavor
        if flavor_id not in self._flavors:
            if ignore_missing:
                return
            raise NotFound(flavor_id)
        del self._flavors[flavor_id]
        self.deleted_flavors.append(flavor_id)

    def delete_service_profile(self, profile, ignore_missing=True):
        profile_id = profile["id"] if isinstance(profile, dict) else profile
        if profile_id not in self._profiles:
            if ignore_missing:
                return
            raise NotFound(profile_id)
        for flavor in self._flavors.values():
            if profile_id in common.service_profile_ids(flavor):
                raise Conflict(profile_id)
        del self._profiles[profile_id]
        self.deleted_profiles.append(profile_id)

    def routers(self, **query):
        flavor_id = query.get("flavor_id")
        routers = self._routers
        if flavor_id:
            routers = [
                router for router in routers if router.get("flavor_id") == flavor_id
            ]
        return iter(routers)


class FakeConnection:
    def __init__(self, network):
        self.network = network


class HookConfigTest(unittest.TestCase):
    def test_hook_config_has_hourly_schedule(self):
        self.assertEqual(
            [
                {
                    "name": "hourly sync",
                    "crontab": common.SYNC_CRONTAB,
                }
            ],
            router_flavors.HOOK_CONFIG["schedule"],
        )


class UpdateFlavorTest(unittest.TestCase):
    def test_ensure_flavor_marks_created_flavor_description(self):
        conn = FakeConnection(FakeNetwork(flavors=[], profiles=[]))

        flavor = update_router_flavors.ensure_flavor(
            conn,
            "pa1410",
            "L3_ROUTER_NAT",
            "Physical PA 1410",
        )

        self.assertEqual(
            common.managed_flavor_description("Physical PA 1410"),
            flavor["description"],
        )

    def test_ensure_flavor_marks_existing_flavor_description(self):
        conn = FakeConnection(
            FakeNetwork(
                flavors=[
                    {
                        "id": "fl-existing",
                        "name": "pa1410",
                        "service_type": "L3_ROUTER_NAT",
                        "description": "Physical PA 1410",
                    },
                ],
                profiles=[],
            )
        )

        flavor = update_router_flavors.ensure_flavor(
            conn,
            "pa1410",
            "L3_ROUTER_NAT",
            "Physical PA 1410",
        )

        self.assertEqual(
            common.managed_flavor_description("Physical PA 1410"),
            flavor["description"],
        )
        self.assertEqual(
            [
                {
                    "id": "fl-existing",
                    "description": common.managed_flavor_description(
                        "Physical PA 1410"
                    ),
                }
            ],
            conn.network.updated_flavors,
        )


class PruneRemovedFlavorsTest(unittest.TestCase):
    def setUp(self):
        self._old_prune = common.PRUNE_REMOVED_FLAVORS
        self._old_delete_profiles = common.DELETE_UNUSED_SERVICE_PROFILES
        self._old_prefixes = common.PRUNE_DRIVER_PREFIXES

        common.PRUNE_REMOVED_FLAVORS = True
        common.DELETE_UNUSED_SERVICE_PROFILES = True
        common.PRUNE_DRIVER_PREFIXES = ("neutron_understack.l3_router.",)

    def tearDown(self):
        common.PRUNE_REMOVED_FLAVORS = self._old_prune
        common.DELETE_UNUSED_SERVICE_PROFILES = self._old_delete_profiles
        common.PRUNE_DRIVER_PREFIXES = self._old_prefixes

    def test_prune_deletes_removed_flavor_and_orphan_profile(self):
        conn = FakeConnection(
            FakeNetwork(
                flavors=[
                    {
                        "id": "fl-keep",
                        "name": "keep",
                        "service_type": "L3_ROUTER_NAT",
                        "service_profile_ids": ["sp-keep"],
                    },
                    {
                        "id": "fl-remove",
                        "name": "remove",
                        "service_type": "L3_ROUTER_NAT",
                        "description": common.managed_flavor_description("remove"),
                        "service_profile_ids": ["sp-remove"],
                    },
                ],
                profiles=[
                    {
                        "id": "sp-keep",
                        "driver": "neutron_understack.l3_router.vrf.Vrf",
                    },
                    {
                        "id": "sp-remove",
                        "driver": "neutron_understack.l3_router.cisco_asa.CiscoAsa",
                        "meta_info": common.OPERATOR_META_INFO_MARKERS,
                    },
                ],
            )
        )

        delete_router_flavors.prune_removed_flavors(conn, [{"name": "keep"}])

        self.assertEqual(["fl-remove"], conn.network.deleted_flavors)
        self.assertEqual(["sp-remove"], conn.network.deleted_profiles)

    def test_prune_deletes_marked_flavor_and_keeps_unmanaged_profile(self):
        conn = FakeConnection(
            FakeNetwork(
                flavors=[
                    {
                        "id": "fl-remove",
                        "name": "remove",
                        "service_type": "L3_ROUTER_NAT",
                        "description": common.managed_flavor_description("remove"),
                        "service_profile_ids": ["sp-external"],
                    },
                ],
                profiles=[
                    {
                        "id": "sp-external",
                        "driver": "neutron_understack.l3_router.cisco_asa.CiscoAsa",
                        "meta_info": {},
                    },
                ],
            )
        )

        delete_router_flavors.prune_removed_flavors(conn, [])

        self.assertEqual(["fl-remove"], conn.network.deleted_flavors)
        self.assertEqual([], conn.network.deleted_profiles)

    def test_prune_skips_unmarked_flavor_with_unmanaged_profile(self):
        conn = FakeConnection(
            FakeNetwork(
                flavors=[
                    {
                        "id": "fl-manual",
                        "name": "manual",
                        "service_type": "L3_ROUTER_NAT",
                        "service_profile_ids": ["sp-manual"],
                    },
                ],
                profiles=[
                    {
                        "id": "sp-manual",
                        "driver": "neutron_understack.l3_router.cisco_asa.CiscoAsa",
                        "meta_info": {},
                    },
                ],
            )
        )

        delete_router_flavors.prune_removed_flavors(conn, [])

        self.assertEqual([], conn.network.deleted_flavors)
        self.assertEqual([], conn.network.deleted_profiles)

    def test_prune_keeps_profile_id_configured_in_current_data(self):
        conn = FakeConnection(
            FakeNetwork(
                flavors=[
                    {
                        "id": "fl-remove",
                        "name": "remove",
                        "service_type": "L3_ROUTER_NAT",
                        "description": common.managed_flavor_description("remove"),
                        "service_profile_ids": ["sp-protected"],
                    },
                ],
                profiles=[
                    {
                        "id": "sp-protected",
                        "driver": "neutron_understack.l3_router.cisco_asa.CiscoAsa",
                    },
                ],
            )
        )

        delete_router_flavors.prune_removed_flavors(
            conn,
            [{"name": "keep", "profile_id": "sp-protected"}],
        )

        self.assertEqual(["fl-remove"], conn.network.deleted_flavors)
        self.assertEqual([], conn.network.deleted_profiles)

    def test_prune_keeps_profile_still_attached_to_another_flavor(self):
        conn = FakeConnection(
            FakeNetwork(
                flavors=[
                    {
                        "id": "fl-keep",
                        "name": "keep",
                        "service_type": "L3_ROUTER_NAT",
                        "service_profile_ids": ["sp-shared"],
                    },
                    {
                        "id": "fl-remove",
                        "name": "remove",
                        "service_type": "L3_ROUTER_NAT",
                        "service_profile_ids": ["sp-shared"],
                    },
                ],
                profiles=[
                    {
                        "id": "sp-shared",
                        "driver": "neutron_understack.l3_router.vrf.Vrf",
                        "meta_info": common.OPERATOR_META_INFO_MARKERS,
                    },
                ],
            )
        )

        delete_router_flavors.prune_removed_flavors(conn, [{"name": "keep"}])

        self.assertEqual(["fl-remove"], conn.network.deleted_flavors)
        self.assertEqual([], conn.network.deleted_profiles)

    def test_prune_skips_removed_flavor_still_used_by_router(self):
        conn = FakeConnection(
            FakeNetwork(
                flavors=[
                    {
                        "id": "fl-remove",
                        "name": "remove",
                        "service_type": "L3_ROUTER_NAT",
                        "service_profile_ids": ["sp-remove"],
                    },
                ],
                profiles=[
                    {
                        "id": "sp-remove",
                        "driver": "neutron_understack.l3_router.cisco_asa.CiscoAsa",
                    },
                ],
                routers=[{"id": "router-1", "flavor_id": "fl-remove"}],
            )
        )

        delete_router_flavors.prune_removed_flavors(conn, [])

        self.assertEqual([], conn.network.deleted_flavors)
        self.assertEqual([], conn.network.deleted_profiles)

    def test_ensure_profile_marks_created_profile_without_configured_id(self):
        conn = FakeConnection(FakeNetwork(flavors=[], profiles=[]))

        profile = create_router_flavors.ensure_profile(
            conn,
            "pa1410",
            "neutron_understack.l3_router.palo_alto.PaloAlto",
            "Physical PA 1410",
            {"resource_class": "pa1410"},
            "",
        )

        meta_info = json.loads(profile["meta_info"])
        self.assertEqual("pa1410", meta_info["resource_class"])
        for key, value in common.OPERATOR_META_INFO_MARKERS.items():
            self.assertEqual(value, meta_info[key])

    def test_matching_profile_ignores_managed_marker(self):
        conn = FakeConnection(
            FakeNetwork(
                flavors=[],
                profiles=[
                    {
                        "id": "sp-managed",
                        "driver": "neutron_understack.l3_router.vrf.Vrf",
                        "meta_info": {
                            "vni_alloc": "auto",
                            **common.OPERATOR_META_INFO_MARKERS,
                        },
                    },
                ],
            )
        )

        profile = create_router_flavors.find_matching_profile(
            conn,
            "neutron_understack.l3_router.vrf.Vrf",
            {"vni_alloc": "auto"},
        )

        self.assertEqual("sp-managed", profile["id"])

    def test_prune_ignores_profiles_outside_driver_scope(self):
        conn = FakeConnection(
            FakeNetwork(
                flavors=[
                    {
                        "id": "fl-external",
                        "name": "external",
                        "service_type": "L3_ROUTER_NAT",
                        "service_profile_ids": ["sp-external"],
                    },
                ],
                profiles=[
                    {
                        "id": "sp-external",
                        "driver": "third.party.Router",
                    },
                ],
            )
        )

        delete_router_flavors.prune_removed_flavors(conn, [])

        self.assertEqual([], conn.network.deleted_flavors)
        self.assertEqual([], conn.network.deleted_profiles)


if __name__ == "__main__":
    unittest.main()
