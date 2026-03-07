"""Undersync ML2 Mechanism Driver.

This driver pushes port configuration data to Undersync when ports are
created, updated, or deleted. It gathers all necessary context from
Neutron to build a complete payload.

This is a simplified driver that only handles the undersync integration,
leaving dynamic segment allocation to networking-baremetal.
"""

import json
import logging
from typing import Any

from neutron.objects.network import NetworkSegment
from neutron_lib.api.definitions import portbindings
from neutron_lib.plugins.ml2.api import MechanismDriver
from oslo_config import cfg

from neutron_understack import config
from neutron_understack.undersync import Undersync

LOG = logging.getLogger(__name__)


class UndersyncPayloadBuilder:
    """Builds the Undersync API payload from Neutron data.

    This class gathers all necessary data from the Neutron database and
    formats it according to the Undersync push API specification.
    """

    def __init__(self, context, vlan_group: str) -> None:
        self.context = context
        self.vlan_group = vlan_group
        self._db_session = None

    @property
    def db_session(self):
        """Get database session from context."""
        if self._db_session is None:
            self._db_session = self.context.session
        return self._db_session

    def build(
        self,
        trigger_event: str,
        trigger_port_id: str | None = None,
        trigger_network_id: str | None = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        """Build the complete Undersync payload."""
        segments = self._get_segments_for_vlan_group()
        segment_ids = {segment["uuid"] for segment in segments}
        network_ids = {segment["network_id"] for segment in segments}
        port_ids = self._get_bound_port_ids_for_segments(segment_ids)
        ports = self._get_ports(network_ids, port_ids)
        subnets = self._get_subnets(network_ids)
        subnetpool_ids = {
            subnet["subnetpool_id"] for subnet in subnets if subnet["subnetpool_id"]
        }
        subnetpools = self._get_subnetpools(subnetpool_ids)
        address_scope_ids = {
            pool["address_scope_id"]
            for pool in subnetpools
            if pool.get("address_scope_id")
        }
        routers = self._get_routers(network_ids)
        router_flavor_ids = {
            router["flavor_id"] for router in routers if router["flavor_id"]
        }

        resources = {
            "networks": self._get_networks(network_ids),
            "ports": ports,
            "connected_ports": self._get_connected_ports(ports),
            "segments": segments,
            "subnets": subnets,
            "network_flavors": self._get_network_flavors(router_flavor_ids),
            "routers": routers,
            "address_scopes": self._get_address_scopes(address_scope_ids),
            "subnetpools": subnetpools,
        }

        payload = {
            "vlan_group": self.vlan_group,
            "trigger": {
                "event": trigger_event,
                "port_id": trigger_port_id,
                "network_id": trigger_network_id,
            },
            "options": {
                "dry_run": dry_run,
                "force": force,
            },
            "resources": resources,
        }
        return payload

    def _get_segments_for_vlan_group(self) -> list[dict[str, Any]]:
        """Get network segments for this VLAN group (physical_network)."""
        segments = (
            self.db_session.query(NetworkSegment)
            .filter(NetworkSegment.physical_network == self.vlan_group)
            .all()
        )

        return [
            {
                "uuid": seg.id,
                "network_id": seg.network_id,
                "network_type": seg.network_type,
                "physical_network": seg.physical_network,
                "segmentation_id": seg.segmentation_id,
            }
            for seg in segments
        ]

    def _get_networks(self, network_ids: set[str]) -> list[dict[str, Any]]:
        """Get networks with their tags."""
        from neutron.db import models_v2

        if not network_ids:
            return []

        networks = (
            self.db_session.query(models_v2.Network)
            .filter(models_v2.Network.id.in_(list(network_ids)))
            .all()
        )

        return [
            {
                "id": net.id,
                "name": net.name,
                "tags": self._get_resource_tags(net.standard_attr_id),
            }
            for net in networks
        ]

    def _get_bound_port_ids_for_segments(self, segment_ids: set[str]) -> set[str]:
        """Get port IDs bound to this VLAN group's network segments."""
        from neutron.plugins.ml2.models import PortBindingLevel

        if not segment_ids:
            return set()

        rows = (
            self.db_session.query(PortBindingLevel.port_id)
            .filter(PortBindingLevel.segment_id.in_(list(segment_ids)))
            .distinct()
            .all()
        )
        return {port_id for (port_id,) in rows}

    def _get_ports(
        self, network_ids: set[str], port_ids: set[str]
    ) -> list[dict[str, Any]]:
        """Get ports connected to this VLAN group's segments."""
        from neutron.db import models_v2

        if not network_ids or not port_ids:
            return []

        ports = (
            self.db_session.query(models_v2.Port)
            .filter(
                models_v2.Port.network_id.in_(list(network_ids)),
                models_v2.Port.id.in_(list(port_ids)),
            )
            .all()
        )
        port_id_list = [port.id for port in ports]
        binding_profiles = self._get_binding_profiles_for_ports(port_id_list)
        trunk_details = self._get_trunk_details_for_ports(port_id_list)

        return [
            {
                "id": port.id,
                "mac_address": port.mac_address,
                "network_id": port.network_id,
                "trunk_details": trunk_details.get(port.id),
                "binding_profile": binding_profiles.get(port.id, {}),
                "device_owner": port.device_owner,
                "device_id": port.device_id,
                "fixed_ips": [
                    {"subnet_id": ip.subnet_id, "ip_address": ip.ip_address}
                    for ip in port.fixed_ips
                ],
            }
            for port in ports
        ]

    def _get_binding_profiles_for_ports(
        self, port_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Get port binding profiles for a list of ports in one query."""
        from neutron.plugins.ml2.models import PortBinding

        if not port_ids:
            return {}

        bindings = (
            self.db_session.query(PortBinding)
            .filter(PortBinding.port_id.in_(port_ids))
            .all()
        )

        profiles: dict[str, dict[str, Any]] = {}
        for binding in bindings:
            profile = self._parse_binding_profile(binding.profile)
            local_links = profile.get("local_link_information", [])
            if not local_links and not profile.get("physical_network"):
                continue

            existing = profiles.get(binding.port_id)
            # Prefer profile with local link data, then with physical_network.
            if existing:
                existing_links = existing.get("local_link_information", [])
                if existing_links:
                    continue
                if not local_links and existing.get("physical_network"):
                    continue
            profiles[binding.port_id] = profile

        return profiles

    def _parse_binding_profile(self, profile: str | dict | None) -> dict[str, Any]:
        if not profile:
            return {}

        parsed = json.loads(profile) if isinstance(profile, str) else profile
        return {
            "local_link_information": parsed.get("local_link_information", []),
            "physical_network": parsed.get("physical_network"),
        }

    def _get_trunk_details_for_ports(
        self, port_ids: list[str]
    ) -> dict[str, dict[str, Any] | None]:
        """Get trunk details for ports in bulk to avoid per-port queries."""
        from neutron.services.trunk import models as trunk_models

        if not port_ids:
            return {}

        trunks = (
            self.db_session.query(trunk_models.Trunk)
            .filter(trunk_models.Trunk.port_id.in_(port_ids))
            .all()
        )
        trunk_by_port_id = {trunk.port_id: trunk for trunk in trunks}
        trunk_ids = [trunk.id for trunk in trunks]

        sub_ports_by_trunk_id: dict[str, list[dict[str, Any]]] = {}
        if trunk_ids:
            sub_ports = (
                self.db_session.query(trunk_models.SubPort)
                .filter(trunk_models.SubPort.trunk_id.in_(trunk_ids))
                .all()
            )
            for sub_port in sub_ports:
                sub_ports_by_trunk_id.setdefault(sub_port.trunk_id, []).append(
                    {
                        "port_id": sub_port.port_id,
                        "segmentation_type": sub_port.segmentation_type,
                        "segmentation_id": sub_port.segmentation_id,
                    }
                )

        trunk_details: dict[str, dict[str, Any] | None] = {}
        for port_id in port_ids:
            trunk = trunk_by_port_id.get(port_id)
            if not trunk:
                trunk_details[port_id] = None
                continue
            trunk_details[port_id] = {
                "sub_ports": sub_ports_by_trunk_id.get(trunk.id, [])
            }
        return trunk_details

    def _get_connected_ports(self, ports: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Get ports with physical switch connections on this VLAN group."""
        connected_ports: list[dict[str, Any]] = []
        for port in ports:
            binding_profile = port.get("binding_profile") or {}
            if not self._is_port_connected_to_vlan_group(binding_profile):
                continue

            connected_ports.append(
                {
                    "id": port["id"],
                    "network_id": port["network_id"],
                    "physical_network": binding_profile.get("physical_network"),
                    "local_link_information": binding_profile.get(
                        "local_link_information", []
                    ),
                }
            )
        return connected_ports

    def _is_port_connected_to_vlan_group(self, binding_profile: dict[str, Any]) -> bool:
        """Check if a port is physically connected to this VLAN group."""
        local_links = binding_profile.get("local_link_information", [])
        if not local_links:
            return False
        return binding_profile.get("physical_network") == self.vlan_group

    def _get_subnets(self, network_ids: set[str]) -> list[dict[str, Any]]:
        """Get subnets with tags."""
        from neutron.db import models_v2

        if not network_ids:
            return []

        subnets = (
            self.db_session.query(models_v2.Subnet)
            .filter(models_v2.Subnet.network_id.in_(list(network_ids)))
            .all()
        )

        return [
            {
                "id": sub.id,
                "network_id": sub.network_id,
                "cidr": sub.cidr,
                "gateway_ip": sub.gateway_ip,
                "router_external": self._is_network_external(sub.network_id),
                "tags": self._get_resource_tags(sub.standard_attr_id),
                "subnetpool_id": sub.subnetpool_id,
            }
            for sub in subnets
        ]

    def _is_network_external(self, network_id: str) -> bool:
        """Check if a network is external."""
        try:
            from neutron.db import external_net_db

            ext = (
                self.db_session.query(external_net_db.ExternalNetwork)
                .filter(external_net_db.ExternalNetwork.network_id == network_id)
                .first()
            )
            return ext is not None
        except Exception:
            return False

    def _get_network_flavors(self, flavor_ids: set[str]) -> list[dict[str, Any]]:
        """Get network flavors used by routers in the VLAN group scope."""
        try:
            from neutron.db import flavors_db

            if not flavor_ids:
                return []

            flavors = (
                self.db_session.query(flavors_db.Flavor)
                .filter(
                    flavors_db.Flavor.id.in_(list(flavor_ids)),
                    flavors_db.Flavor.service_type == "L3_ROUTER_NAT",
                )
                .all()
            )

            return [
                {
                    "id": f.id,
                    "name": f.name,
                    "service_type": f.service_type,
                    "enabled": f.enabled,
                }
                for f in flavors
            ]
        except Exception as e:
            LOG.warning("Failed to fetch network flavors: %s", e)
            return []

    def _get_routers(self, network_ids: set[str]) -> list[dict[str, Any]]:
        """Get routers that have interfaces in our networks."""
        from neutron.db import l3_db
        from neutron.db import models_v2

        if not network_ids:
            return []

        router_ports = (
            self.db_session.query(models_v2.Port)
            .filter(
                models_v2.Port.network_id.in_(list(network_ids)),
                models_v2.Port.device_owner == "network:router_interface",
            )
            .all()
        )

        router_ids = {p.device_id for p in router_ports}
        if not router_ids:
            return []

        routers = (
            self.db_session.query(l3_db.Router)
            .filter(l3_db.Router.id.in_(list(router_ids)))
            .all()
        )

        return [
            {"id": r.id, "flavor_id": getattr(r, "flavor_id", None)} for r in routers
        ]

    def _get_address_scopes(self, address_scope_ids: set[str]) -> list[dict[str, Any]]:
        """Get address scopes used by subnet pools in scope."""
        try:
            from neutron.db import address_scope_db

            if not address_scope_ids:
                return []

            scopes = (
                self.db_session.query(address_scope_db.AddressScope)
                .filter(address_scope_db.AddressScope.id.in_(list(address_scope_ids)))
                .all()
            )
            return [{"id": s.id, "name": s.name} for s in scopes]
        except Exception as e:
            LOG.warning("Failed to fetch address scopes: %s", e)
            return []

    def _get_subnetpools(self, subnetpool_ids: set[str]) -> list[dict[str, Any]]:
        """Get subnet pools referenced by subnets in scope."""
        try:
            from neutron.db import models_v2

            if not subnetpool_ids:
                return []

            pools = (
                self.db_session.query(models_v2.SubnetPool)
                .filter(models_v2.SubnetPool.id.in_(list(subnetpool_ids)))
                .all()
            )
            return [{"id": p.id, "address_scope_id": p.address_scope_id} for p in pools]
        except Exception as e:
            LOG.warning("Failed to fetch subnet pools: %s", e)
            return []

    def _get_resource_tags(self, standard_attr_id: int) -> list[str]:
        """Get tags for a resource by its standard_attr_id."""
        try:
            from neutron.db import tag_db as tag_model

            tags = (
                self.db_session.query(tag_model.Tag)
                .filter(tag_model.Tag.standard_attr_id == standard_attr_id)
                .all()
            )
            return [t.tag for t in tags]
        except Exception:
            return []


class UndersyncMechanismDriver(MechanismDriver):
    """ML2 Mechanism Driver that pushes port data to Undersync.

    This driver listens for port lifecycle events and pushes the relevant
    configuration data to Undersync, which then configures the physical
    switches.

    Unlike the full UnderstackDriver, this driver:
    - Does NOT handle dynamic segment allocation (use networking-baremetal)
    - Does NOT bind ports
    - ONLY pushes Neutron state to undersync for switch configuration
    """

    @property
    def connectivity(self):
        # This driver doesn't provide connectivity itself
        return None

    def initialize(self):
        config.register_ml2_understack_opts(cfg.CONF)
        conf = cfg.CONF.ml2_understack
        self.undersync = Undersync(conf.undersync_token, conf.undersync_url)
        self.dry_run = conf.undersync_dry_run
        LOG.info("UndersyncMechanismDriver initialized")

    def _get_vlan_group(self, context, port: dict | None = None) -> str | None:
        """Extract the VLAN group (physical_network) from port context.

        Args:
            context: The ML2 port context
            port: Optional port dict to use instead of context.current
                  (useful for delete operations where current may be empty)
        """
        # Use provided port or fall back to context.current
        if port is None:
            port = context.current

        # Try to get from binding profile first
        binding_profile = port.get(portbindings.PROFILE) or {}
        physical_network = binding_profile.get("physical_network")
        if physical_network:
            return physical_network

        # Fall back to segment
        segment = context.bottom_bound_segment or context.top_bound_segment
        if segment:
            return segment.get("physical_network")

        return None

    def _should_process(self, context) -> bool:
        """Determine if this port event should trigger an Undersync sync."""
        port = context.current
        binding_profile = port.get(portbindings.PROFILE) or {}
        local_links = binding_profile.get("local_link_information", [])

        # Only process ports with physical switch bindings
        if not local_links:
            return False

        # Must have a VLAN group to sync
        if not self._get_vlan_group(context):
            return False

        return True

    def _trigger_sync(self, context, event: str, port: dict | None = None):
        """Trigger an Undersync sync for the given port event."""
        if port is None:
            port = context.current

        vlan_group = self._get_vlan_group(context, port=port)
        if not vlan_group:
            LOG.warning(
                "Could not determine VLAN group for port %s",
                port.get("id"),
            )
            return

        plugin_context = getattr(context, "_plugin_context", None)
        if plugin_context is None:
            LOG.warning(
                "Could not build Undersync payload for port %s: missing plugin context",
                port.get("id"),
            )
            return

        try:
            builder = UndersyncPayloadBuilder(
                plugin_context,
                vlan_group,
            )
            payload = builder.build(
                trigger_event=event,
                trigger_port_id=port.get("id"),
                trigger_network_id=port.get("network_id"),
                dry_run=self.dry_run,
            )

            self.undersync.sync_with_payload(vlan_group, payload)
            LOG.info(
                "Undersync sync completed for VLAN group %s (event=%s, port=%s)",
                vlan_group,
                event,
                port.get("id"),
            )

        except Exception:
            LOG.exception(
                "Undersync sync failed for port %s",
                port.get("id"),
            )

    # =========================================================================
    # ML2 API Methods
    # =========================================================================

    def create_network_precommit(self, context):
        pass

    def create_network_postcommit(self, context):
        pass

    def update_network_precommit(self, context):
        pass

    def update_network_postcommit(self, context):
        pass

    def delete_network_precommit(self, context):
        pass

    def delete_network_postcommit(self, context):
        pass

    def create_subnet_precommit(self, context):
        pass

    def create_subnet_postcommit(self, context):
        pass

    def update_subnet_precommit(self, context):
        pass

    def update_subnet_postcommit(self, context):
        pass

    def delete_subnet_precommit(self, context):
        pass

    def delete_subnet_postcommit(self, context):
        pass

    def create_port_precommit(self, context):
        pass

    def create_port_postcommit(self, context):
        """Called after port creation is committed."""
        if self._should_process(context):
            self._trigger_sync(context, "port_create")

    def update_port_precommit(self, context):
        pass

    def update_port_postcommit(self, context):
        """Called after port update is committed."""
        if self._should_process(context):
            self._trigger_sync(context, "port_update")

    def delete_port_precommit(self, context):
        pass

    def delete_port_postcommit(self, context):
        """Called after port deletion is committed."""
        # For delete, check original context since current may be empty
        port = context.original or context.current
        binding_profile = port.get(portbindings.PROFILE) or {}
        local_links = binding_profile.get("local_link_information", [])

        if local_links:
            self._trigger_sync(context, "port_delete", port=port)

    def bind_port(self, context):
        # This driver doesn't bind ports - use networking-baremetal for that
        pass

    def check_vlan_transparency(self, context):
        pass
