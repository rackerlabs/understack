"""Tests for NeutronSegmentRange spec validation.

Focus on ``_validate_spec``, the cross-field rule the CRD cannot express:
VLAN ranges require ``physical_network`` while tunnelled types
(``vxlan``/``gre``/``geneve``) must omit it. ``flat`` is intentionally not a
supported network type -- Neutron's segment range API only accepts
vlan/vxlan/gre/geneve -- so it is neither in the CRD enum nor treated as a
physical-network type here.
"""

from __future__ import annotations

from typing import Any

import pytest

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.neutron.segment_ranges import reconcile
from openstack_sync.plugins.neutron.segment_ranges.config import (
    PHYSICAL_NETWORK_TYPES,
)
from openstack_sync.plugins.neutron.segment_ranges.config import TUNNEL_NETWORK_TYPES


def _spec(**overrides: Any) -> dict[str, Any]:
    """A minimally valid shared VLAN spec; override fields per test."""
    spec: dict[str, Any] = {
        "name": "example-range",
        "network_type": "vlan",
        "physical_network": "physnet1",
        "minimum": 100,
        "maximum": 200,
        "shared": True,
    }
    spec.update(overrides)
    return spec


# ---------------------------------------------------------------------------
# Network-type classification: the sets my change touched
# ---------------------------------------------------------------------------


def test_flat_is_not_a_physical_network_type():
    """``flat`` is unsupported and must not be classified as physical."""
    assert "flat" not in PHYSICAL_NETWORK_TYPES
    assert "flat" not in TUNNEL_NETWORK_TYPES


def test_vlan_is_the_only_physical_network_type():
    assert PHYSICAL_NETWORK_TYPES == frozenset({"vlan"})


def test_tunnel_types_are_exactly_vxlan_gre_geneve():
    assert TUNNEL_NETWORK_TYPES == frozenset({"vxlan", "gre", "geneve"})


# ---------------------------------------------------------------------------
# _validate_spec: physical-network cross-field rule
# ---------------------------------------------------------------------------


def test_valid_vlan_spec_passes():
    reconcile._validate_spec(_spec())


def test_vlan_without_physical_network_is_rejected():
    with pytest.raises(ConfigError, match="requires physical_network"):
        reconcile._validate_spec(_spec(physical_network=None))


def test_vlan_with_empty_physical_network_is_rejected():
    with pytest.raises(ConfigError, match="requires physical_network"):
        reconcile._validate_spec(_spec(physical_network=""))


@pytest.mark.parametrize("network_type", ["vxlan", "gre", "geneve"])
def test_tunnel_type_without_physical_network_passes(network_type: str):
    spec = _spec(network_type=network_type)
    spec.pop("physical_network")
    reconcile._validate_spec(spec)


@pytest.mark.parametrize("network_type", ["vxlan", "gre", "geneve"])
def test_tunnel_type_with_physical_network_is_rejected(network_type: str):
    with pytest.raises(ConfigError, match="must not set physical_network"):
        reconcile._validate_spec(
            _spec(network_type=network_type, physical_network="physnet1")
        )


# ---------------------------------------------------------------------------
# _validate_spec: range and project rules (guards the rest of the function)
# ---------------------------------------------------------------------------


def test_minimum_greater_than_maximum_is_rejected():
    with pytest.raises(ConfigError, match="the range is empty"):
        reconcile._validate_spec(_spec(minimum=300, maximum=200))


def test_equal_minimum_and_maximum_passes():
    reconcile._validate_spec(_spec(minimum=100, maximum=100))


def test_unshared_range_without_project_id_is_rejected():
    with pytest.raises(ConfigError, match="project_id is required"):
        reconcile._validate_spec(_spec(shared=False))


def test_unshared_range_with_project_id_passes():
    reconcile._validate_spec(_spec(shared=False, project_id="proj-1"))
