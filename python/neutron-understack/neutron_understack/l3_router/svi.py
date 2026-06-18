import logging

from neutron.services.l3_router.service_providers import base
from neutron_lib import constants as const
from neutron_lib import exceptions as n_exc
from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.plugins import constants as plugin_constants
from neutron_lib.plugins import directory

LOG = logging.getLogger(__name__)

# Full dotted path as stored in the flavor profile's service_providers table.
# Must match the value in understack/components/neutron/values.yaml.
SVI_DRIVER = "neutron_understack.l3_router.svi.Svi"


def _is_svi_router(context, router):
    flavor_id = router.get("flavor_id")
    if not flavor_id or flavor_id is const.ATTR_NOT_SPECIFIED:
        LOG.debug("SVI check: router %s has no flavor, skipping", router.get("id"))
        return False
    flavor_plugin = directory.get_plugin(plugin_constants.FLAVORS)
    flavor = flavor_plugin.get_flavor(context, flavor_id)
    provider = flavor_plugin.get_flavor_next_provider(context, flavor["id"])[0]
    driver = provider["driver"]
    is_svi = driver == SVI_DRIVER
    LOG.debug(
        "SVI check: router %s flavor %s driver %s is_svi=%s",
        router.get("id"),
        flavor_id,
        driver,
        is_svi,
    )
    return is_svi


def _get_subnet_address_scope(context, subnet_id):
    """Return (ip_version, address_scope_id). scope is None if not set."""
    core_plugin = directory.get_plugin()
    subnet = core_plugin.get_subnet(context, subnet_id)
    ip_version = subnet.get("ip_version")
    subnetpool_id = subnet.get("subnetpool_id")
    if not subnetpool_id:
        LOG.debug("Subnet %s has no subnetpool, no address scope", subnet_id)
        return ip_version, None
    subnetpool = core_plugin.get_subnetpool(context, subnetpool_id)
    scope_id = subnetpool.get("address_scope_id")
    LOG.debug(
        "Subnet %s subnetpool %s address_scope %s (IPv%s)",
        subnet_id,
        subnetpool_id,
        scope_id,
        ip_version,
    )
    return ip_version, scope_id


def _get_existing_router_subnet_ids(context, router_id):
    """Return subnet IDs of all internal interfaces already on the router."""
    core_plugin = directory.get_plugin()
    ports = core_plugin.get_ports(
        context,
        filters={
            "device_id": [router_id],
            "device_owner": [const.DEVICE_OWNER_ROUTER_INTF],
        },
    )
    subnet_ids = [
        ip["subnet_id"]
        for port in ports
        for ip in port.get("fixed_ips", [])
        if ip.get("subnet_id")
    ]
    LOG.debug(
        "Router %s already has %d subnet(s): %s",
        router_id,
        len(subnet_ids),
        subnet_ids,
    )
    return subnet_ids


def _validate_address_scope_rules(context, router_id, new_subnet_ids):
    """Validate address scope rules for subnets being attached to an SVI router.

    Raises BadRequest if any subnet has no scope or conflicts with existing ones.
    Returns {ip_version: scope_id} for the new subnets.
    """
    new_scopes: dict[int, str] = {}
    LOG.debug(
        "SVI scope check: router %s validating new subnet(s)=%s",
        router_id,
        new_subnet_ids,
    )

    # Rule 1: every new subnet must belong to an address scope
    for subnet_id in new_subnet_ids:
        ip_version, scope_id = _get_subnet_address_scope(context, subnet_id)
        if not scope_id:
            LOG.warning(
                "SVI scope check FAILED: subnet %s has no address scope (router %s)",
                subnet_id,
                router_id,
            )
            raise n_exc.BadRequest(
                resource="router",
                msg=(
                    f"Subnet {subnet_id} must belong to an address scope "
                    "to attach to an SVI router."
                ),
            )
        if ip_version in new_scopes and new_scopes[ip_version] != scope_id:
            LOG.warning(
                "SVI scope check FAILED: IPv%s conflict in new attach on router %s - "
                "subnet %s scope=%s previous_scope=%s",
                ip_version,
                router_id,
                subnet_id,
                scope_id,
                new_scopes[ip_version],
            )
            raise n_exc.BadRequest(
                resource="router",
                msg=(
                    f"Cannot attach subnets {new_subnet_ids!r}: IPv{ip_version} "
                    f"address scope {scope_id!r} differs from scope "
                    f"{new_scopes[ip_version]!r} in the same request."
                ),
            )
        new_scopes[ip_version] = scope_id
        LOG.debug(
            "SVI scope check resolved: router %(router)s subnet %(subnet)s "
            "IPv%(ip_version)s scope %(scope)s",
            {
                "router": router_id,
                "subnet": subnet_id,
                "ip_version": ip_version,
                "scope": scope_id,
            },
        )

    LOG.debug(
        "SVI scope check requested scopes: router %(router)s scopes=%(scopes)s",
        {"router": router_id, "scopes": new_scopes},
    )

    # Rule 2: must not conflict with existing interfaces (per IP version)
    for existing_subnet_id in _get_existing_router_subnet_ids(context, router_id):
        ip_version, existing_scope = _get_subnet_address_scope(
            context, existing_subnet_id
        )
        if ip_version not in new_scopes:
            LOG.debug(
                "SVI scope check compare skipped: router %(router)s existing "
                "subnet %(subnet)s is IPv%(ip_version)s with no new subnet in "
                "that IP family",
                {
                    "router": router_id,
                    "subnet": existing_subnet_id,
                    "ip_version": ip_version,
                },
            )
            continue
        LOG.debug(
            "SVI scope check compare: router %(router)s IPv%(ip_version)s "
            "new_scope=%(new_scope)s existing_scope=%(existing_scope)s "
            "existing_subnet=%(subnet)s",
            {
                "router": router_id,
                "ip_version": ip_version,
                "new_scope": new_scopes[ip_version],
                "existing_scope": existing_scope,
                "subnet": existing_subnet_id,
            },
        )
        if not existing_scope:
            LOG.warning(
                "SVI scope check FAILED: existing IPv%s subnet %s on router %s "
                "has no address scope",
                ip_version,
                existing_subnet_id,
                router_id,
            )
            raise n_exc.BadRequest(
                resource="router",
                msg=(
                    f"Existing subnet {existing_subnet_id} on router {router_id} "
                    "must belong to an address scope before attaching more "
                    "subnets to an SVI router."
                ),
            )
        if existing_scope != new_scopes[ip_version]:
            LOG.warning(
                "SVI scope check FAILED: IPv%s conflict on router %s - "
                "new=%s existing=%s (from subnet %s)",
                ip_version,
                router_id,
                new_scopes[ip_version],
                existing_scope,
                existing_subnet_id,
            )
            raise n_exc.BadRequest(
                resource="router",
                msg=(
                    f"Cannot attach subnet {new_subnet_ids!r}: its IPv{ip_version} "
                    f"address scope {new_scopes[ip_version]!r} differs from "
                    f"scope {existing_scope!r} already in use on router {router_id}."
                ),
            )

    return new_scopes


def validate_svi_router_port(plugin_context, port):
    """Standalone SVI scope validator called from create_port_precommit.

    Fires before port is committed, so invalid subnets never reach the VLAN
    allocation / trunk / Undersync steps in create_port_postcommit.
    Raises BadRequest if validation fails.
    Returns True when an SVI router interface was validated, otherwise False.
    """
    device_owner = port.get("device_owner")
    if device_owner != const.DEVICE_OWNER_ROUTER_INTF:
        LOG.debug(
            "precommit SVI scope check skipped: port %s owner %s is not an "
            "internal router interface",
            port.get("id"),
            device_owner,
        )
        return False

    router_id = port.get("device_id")
    if not router_id:
        return False

    try:
        l3_plugin = directory.get_plugin(plugin_constants.L3)
        router = l3_plugin.get_router(plugin_context, router_id)
    except Exception:
        LOG.exception(
            "precommit SVI scope check failed to fetch router %s for port %s",
            router_id,
            port.get("id"),
        )
        raise

    if not _is_svi_router(plugin_context, router):
        LOG.debug(
            "precommit SVI scope check skipped: router %(router)s is not SVI "
            "(name=%(name)s flavor=%(flavor)s) for port %(port)s",
            {
                "router": router_id,
                "name": router.get("name"),
                "flavor": router.get("flavor_id"),
                "port": port.get("id"),
            },
        )
        return False

    new_subnet_ids = [
        ip["subnet_id"] for ip in port.get("fixed_ips", []) if ip.get("subnet_id")
    ]
    LOG.info(
        "precommit SVI scope check: router %s (%s) port %s network %s subnet(s)=%s",
        router_id,
        router.get("name"),
        port.get("id"),
        port.get("network_id"),
        new_subnet_ids,
    )

    new_scopes = _validate_address_scope_rules(
        plugin_context, router_id, new_subnet_ids
    )

    LOG.info(
        "precommit SVI scope check PASSED: router %s port %s subnet(s)=%s scopes=%s",
        router_id,
        port.get("id"),
        new_subnet_ids,
        new_scopes,
    )
    return True


@registry.has_registry_receivers
class Svi(base.L3ServiceProvider):
    ha_support = base.OPTIONAL

    def __init__(self, l3_plugin):
        super().__init__(l3_plugin)
        LOG.info("SVI service provider initialized: driver=%r", SVI_DRIVER)

    @registry.receives(resources.ROUTER_INTERFACE, [events.BEFORE_CREATE])
    def _validate_svi_router_interface(self, _resource, _event, _trigger, payload):
        router = payload.states[0]
        context = payload.context
        router_id = payload.resource_id

        if not _is_svi_router(context, router):
            LOG.debug(
                "SVI callback validation skipped: router %(router)s is not SVI "
                "(name=%(name)s flavor=%(flavor)s)",
                {
                    "router": router_id,
                    "name": router.get("name"),
                    "flavor": router.get("flavor_id"),
                },
            )
            return

        port = payload.metadata["port"]
        new_subnet_ids = [
            ip["subnet_id"] for ip in port.get("fixed_ips", []) if ip.get("subnet_id")
        ]
        LOG.info(
            "SVI callback validation: router %s (%s) port %s network %s "
            "owner %s subnet(s)=%s",
            router_id,
            router.get("name"),
            port.get("id"),
            port.get("network_id"),
            port.get("device_owner"),
            new_subnet_ids,
        )

        new_scopes = _validate_address_scope_rules(context, router_id, new_subnet_ids)

        LOG.info(
            "SVI callback validation PASSED: router %s port %s subnet(s)=%s scopes=%s",
            router_id,
            port.get("id"),
            new_subnet_ids,
            new_scopes,
        )
