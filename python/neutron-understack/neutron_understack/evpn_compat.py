"""Compatibility helpers for the EVPN router extension.

The EVPN router feature (the ``evpn_vni`` attribute, its API extension and its
policies) was upstreamed into neutron. On a neutron that carries it (e.g. the
understack/2026.1 branch) core provides all of:

* ``neutron_lib.api.definitions.evpn`` -- the router ``evpn_vni`` attribute
* ``neutron.extensions.evpn``          -- the API extension
* ``neutron.conf.policies.evpn``       -- the create/get ``router:evpn_vni`` policies

If ``neutron_understack`` also registers any of these, neutron-server fails at
startup -- most visibly ``DuplicatePolicyError`` raised from
``neutron.policy.register_rules()``, which aborts policy initialization for the
whole service. When core owns EVPN, Understack must register none of them and
contribute only its runtime VNI allocation (the service-plugin callbacks).

Every surface that would otherwise register an EVPN artifact keys off
``core_provides_evpn()`` so the decision is made in exactly one place.
"""

from neutron.conf import policies as core_policies

from neutron_understack.api.definitions import understack_vni

try:
    from neutron_lib.api.definitions import evpn as core_evpn_apidef
except ImportError:
    core_evpn_apidef = None

# The router EVPN policy name core registers when it owns the feature. This is
# also the exact rule neutron_understack would otherwise re-register, so its
# presence in core's policy list is what triggers the DuplicatePolicyError.
_CORE_EVPN_POLICY = "create_router:evpn_vni"


def core_provides_evpn():
    """Return True when neutron core registers the EVPN router feature itself.

    Checks the actual policy list neutron.policy.register_rules() consumes
    (``neutron.conf.policies.list_rules()``), rather than merely whether the
    extension module is importable -- core registers these policies
    unconditionally at startup, independent of which extensions are loaded.
    """
    return any(rule.name == _CORE_EVPN_POLICY for rule in core_policies.list_rules())


def api_definition():
    """The api-definition to use for the router VNI extension.

    Prefer core's ``evpn`` api-definition when core owns the feature so the
    ``evpn_vni`` attribute is defined exactly once; otherwise fall back to
    Understack's own definition.
    """
    if core_provides_evpn() and core_evpn_apidef is not None:
        return core_evpn_apidef
    return understack_vni
