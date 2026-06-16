import logging

from neutron.services.ovn_l3.service_providers.user_defined import UserDefined
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
# https://github.com/openstack/neutron-lib.
ROUTER_INTERFACE_OWNERS = [
    const.DEVICE_OWNER_ROUTER_INTF,
    const.DEVICE_OWNER_ROUTER_GW,
]
# Doug told SVI should never have an external interface will circle back here.


def _is_svi_router(context, router):
    # Will test on dev
    # Cannot use UserDefined._is_user_defined_provider() — it builds the driver
    # string using __name__ of the UserDefined module, producing
    # neutron.services...user_defined.Svi instead of
    # neutron_understack.l3_router.svi.Svi, so the lookup always fails.
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
    #  LOG.debug(
    # Message: 'SVI check: router %s flavor %s driver %s \u2192 is_svi=%s'
    # Arguments: ('f6bc7061-023e-4fb8-956c-3cd1d5d04022',
    #             'e07c2c5f-9ac2-479a-a2ac-923872d0aff6',
    #             'neutron_understack.l3_router.svi.Svi', True)


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
    """Return subnet IDs of all interfaces already on the router."""
    core_plugin = directory.get_plugin()
    ports = core_plugin.get_ports(
        context,
        filters={
            "device_id": [router_id],
            "device_owner": ROUTER_INTERFACE_OWNERS,
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


def validate_svi_router_port(plugin_context, port):
    """Standalone SVI scope validator — called from create_port_precommit.

    Fires before port is committed, so invalid subnets never reach the VLAN
    allocation / trunk / Undersync steps in create_port_postcommit.
    Raises BadRequest if validation fails (wrapped as MechanismDriverError
    by _call_on_drivers → HTTP 500, but the message is still user-readable).
    """
    device_owner = port.get("device_owner")
    if device_owner not in ROUTER_INTERFACE_OWNERS:
        LOG.debug(
            "validate_svi_router_port: skipping port %s with owner %s",
            port.get("id"),
            device_owner,
        )
        return
    router_id = port.get("device_id")
    if not router_id:
        return

    try:
        l3_plugin = directory.get_plugin(plugin_constants.L3)
        router = l3_plugin.get_router(plugin_context, router_id)
    except Exception:
        LOG.debug(
            "validate_svi_router_port: could not fetch router %s, skipping",
            router_id,
        )
        return

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
        return

    if device_owner == const.DEVICE_OWNER_ROUTER_GW:
        LOG.warning(
            "precommit SVI: router %s (%s) is receiving a gateway port (owner=%s) "
            "— SVI routers should not have external interfaces "
            "Allowing for testing will come back here ",
            router_id,
            router.get("name"),
            device_owner,
        )

    new_subnet_ids = [
        ip["subnet_id"] for ip in port.get("fixed_ips", []) if ip.get("subnet_id")
    ]
    LOG.info(
        "precommit SVI scope check: router %(router)s (%(name)s) port %(port)s "
        "network %(network)s owner %(owner)s fixed_ips=%(fixed_ips)s "
        "subnet(s)=%(subnets)s",
        {
            "router": router_id,
            "name": router.get("name"),
            "port": port.get("id"),
            "network": port.get("network_id"),
            "owner": port.get("device_owner"),
            "fixed_ips": port.get("fixed_ips", []),
            "subnets": new_subnet_ids,
        },
    )

    new_scopes: dict[int, str] = {}
    for subnet_id in new_subnet_ids:
        ip_version, scope_id = _get_subnet_address_scope(plugin_context, subnet_id)
        if not scope_id:
            LOG.warning(
                "precommit SVI FAILED: subnet %s has no address scope (router %s)",
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
        new_scopes[ip_version] = scope_id
        LOG.debug(
            "precommit SVI scope resolved: router %(router)s subnet %(subnet)s "
            "IPv%(ip_version)s scope %(scope)s",
            {
                "router": router_id,
                "subnet": subnet_id,
                "ip_version": ip_version,
                "scope": scope_id,
            },
        )

    LOG.debug(
        "precommit SVI requested scopes: router %(router)s scopes=%(scopes)s",
        {"router": router_id, "scopes": new_scopes},
    )

    for existing_subnet_id in _get_existing_router_subnet_ids(
        plugin_context, router_id
    ):
        ip_version, existing_scope = _get_subnet_address_scope(
            plugin_context, existing_subnet_id
        )
        if ip_version not in new_scopes:
            LOG.debug(
                "precommit SVI compare skipped: router %(router)s existing "
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
            "precommit SVI compare: router %(router)s IPv%(ip_version)s "
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
        if existing_scope and existing_scope != new_scopes[ip_version]:
            LOG.warning(
                "precommit SVI FAILED: IPv%s scope conflict on router %s — "
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

    LOG.info(
        "precommit SVI scope check PASSED: router %(router)s port %(port)s "
        "subnet(s)=%(subnets)s scopes=%(scopes)s",
        {
            "router": router_id,
            "port": port.get("id"),
            "subnets": new_subnet_ids,
            "scopes": new_scopes,
        },
    )


@registry.has_registry_receivers
class Svi(UserDefined):
    def __init__(self, l3_plugin):
        super().__init__(l3_plugin)
        LOG.info(
            "SVI service provider initialized: inherited_provider=%r "
            "expected_driver=%r",
            self._user_defined_provider,
            SVI_DRIVER,
        )

    @registry.receives(resources.ROUTER_INTERFACE, [events.BEFORE_CREATE])
    def _validate_svi_router_interface(self, _resource, _event, _trigger, payload):
        router = payload.states[0]
        context = payload.context
        router_id = payload.resource_id

        LOG.debug("SVI validation triggered: router_id=%s", router_id)

        # _is_user_defined_provider works (from user_defined.py ):
        #   flavor = get_flavor(context, router['flavor_id'])
        #   provider = get_flavor_next_provider(context, flavor['id'])[0]
        #   return str(provider['driver']) == self._user_defined_provider
        #
        # self._user_defined_provider is set in __init__ (line 43):
        #   self._user_defined_provider = __name__ + "." + self.__class__.__name__
        #
        # __name__ is the MODULE-LEVEL variable captured inside user_defined.py,
        # so it is always "neutron.services.ovn_l3.service_providers.user_defined"
        # regardless of which subclass calls it.
        #
        # For our Svi class that means:
        #   neutron.services.ovn_l3.service_providers.user_defined.Svi
        # But provider['driver'] in the flavor profile stores:
        #   "neutron_understack.l3_router.svi.Svi"
        # comparison fails and always returns False for our subclass.

        # Standalone helper: compares provider['driver'] against
        # SVI_DRIVER = "neutron_understack.l3_router.svi.Svi" directly
        result_our_check = _is_svi_router(context, router)

        # Parent class method: broken for subclasses, kept here for tracing.
        result_parent_check = self._is_user_defined_provider(context, router)

        # Log the raw strings so we can see exactly what is compared
        LOG.info(
            "SVI router detection — router=%s | "
            "self._user_defined_provider=%r | "
            "SVI_DRIVER=%r | "
            "_is_svi_router()=%s | _is_user_defined_provider()=%s",
            router_id,
            self._user_defined_provider,  # built from __name__ of UserDefined module
            SVI_DRIVER,  # our hardcoded constant
            result_our_check,
            result_parent_check,
        )
        if result_our_check != result_parent_check:
            LOG.warning(
                "SVI detection MISMATCH on router %s: "
                "_is_svi_router=%s but _is_user_defined_provider=%s | "
                "parent built %r but flavor stores %r",
                router_id,
                result_our_check,
                result_parent_check,
                self._user_defined_provider,
                SVI_DRIVER,
            )

        if not result_our_check:
            LOG.debug(
                "Router %s is not an SVI router, skipping scope validation",
                router_id,
            )
            return

        port = payload.metadata["port"]
        new_subnet_ids = [
            ip["subnet_id"] for ip in port.get("fixed_ips", []) if ip.get("subnet_id")
        ]
        LOG.info(
            "SVI callback validation: router %(router)s (%(name)s) port %(port)s "
            "network %(network)s owner %(owner)s subnet(s)=%(subnets)s",
            {
                "router": router_id,
                "name": router.get("name"),
                "port": port.get("id"),
                "network": port.get("network_id"),
                "owner": port.get("device_owner"),
                "subnets": new_subnet_ids,
            },
        )

        # Rule 1: every new subnet must belong to an address scope
        new_scopes: dict[int, str] = {}
        for subnet_id in new_subnet_ids:
            ip_version, scope_id = _get_subnet_address_scope(context, subnet_id)
            if not scope_id:
                LOG.warning(
                    "SVI validation FAILED: subnet %s has no address scope (router %s)",
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
            new_scopes[ip_version] = scope_id
            LOG.debug(
                "SVI callback resolved: router %(router)s subnet %(subnet)s "
                "IPv%(ip_version)s scope %(scope)s",
                {
                    "router": router_id,
                    "subnet": subnet_id,
                    "ip_version": ip_version,
                    "scope": scope_id,
                },
            )
        LOG.debug(
            "SVI rule 1 passed: router %(router)s scopes=%(scopes)s",
            {"router": router_id, "scopes": new_scopes},
        )

        # Rule 2: all subnets on the router must share the same scope per IP version
        for existing_subnet_id in _get_existing_router_subnet_ids(context, router_id):
            ip_version, existing_scope = _get_subnet_address_scope(
                context, existing_subnet_id
            )
            if ip_version not in new_scopes:
                LOG.debug(
                    "SVI callback compare skipped: router %(router)s existing "
                    "subnet %(subnet)s is IPv%(ip_version)s with no new subnet "
                    "in that IP family",
                    {
                        "router": router_id,
                        "subnet": existing_subnet_id,
                        "ip_version": ip_version,
                    },
                )
                continue
            LOG.debug(
                "SVI callback compare: router %(router)s IPv%(ip_version)s "
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
            if existing_scope and existing_scope != new_scopes[ip_version]:
                LOG.warning(
                    "SVI validation FAILED: IPv%s scope conflict on router %s — "
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
                        f"scope {existing_scope!r} already in use on router "
                        f"{router_id}."
                    ),
                )

        LOG.info(
            "SVI callback validation PASSED: router %(router)s port %(port)s "
            "subnet(s)=%(subnets)s scopes=%(scopes)s",
            {
                "router": router_id,
                "port": port.get("id"),
                "subnets": new_subnet_ids,
                "scopes": new_scopes,
            },
        )
