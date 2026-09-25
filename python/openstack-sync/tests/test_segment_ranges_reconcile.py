"""Tests for NeutronSegmentRange spec validation.

Focus on ``_validate_spec``, the cross-field rule the CRD cannot express:
VLAN ranges require ``physical_network`` while tunnelled types
(``vxlan``/``gre``/``geneve``) must omit it.
"""

from __future__ import annotations

from typing import Any

import pytest

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.neutron.segment_ranges import reconcile
from openstack_sync.plugins.neutron.segment_ranges.config import PHYSICAL_NETWORK_TYPES
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


# ---------------------------------------------------------------------------
# _immutable_drift: Neutron normalizes non-VLAN ranges to physical_network=""
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("network_type", ["vxlan", "gre", "geneve"])
def test_tunnel_range_stored_with_empty_physical_network_is_not_drift(
    network_type: str,
):
    """A tunnelled spec omits physical_network; Neutron stores it as "".

    Without normalization every reconcile would report immutable drift against
    the range the operator itself created.
    """
    spec = _spec(network_type=network_type)
    spec.pop("physical_network")
    existing = {
        "network_type": network_type,
        "physical_network": "",
    }

    assert reconcile._immutable_drift(existing, spec) is None


@pytest.mark.parametrize("stored", [None, ""])
def test_tunnel_range_with_unset_physical_network_is_not_drift(stored: Any):
    """Treat both None and "" as unset, whichever the SDK hands back."""
    spec = _spec(network_type="vxlan")
    spec.pop("physical_network")

    assert (
        reconcile._immutable_drift(
            {"network_type": "vxlan", "physical_network": stored}, spec
        )
        is None
    )


def test_matching_vlan_range_is_not_drift():
    existing = {"network_type": "vlan", "physical_network": "physnet1"}

    assert reconcile._immutable_drift(existing, _spec()) is None


def test_physical_network_mismatch_is_drift():
    existing = {"network_type": "vlan", "physical_network": "physnet2"}

    drift = reconcile._immutable_drift(existing, _spec())

    assert drift is not None
    assert "physical_network" in drift


def test_network_type_mismatch_is_drift():
    existing = {"network_type": "vxlan", "physical_network": ""}

    drift = reconcile._immutable_drift(existing, _spec())

    assert drift is not None
    assert "network_type" in drift


# ---------------------------------------------------------------------------
# _immutable_drift: shared and project_id are allow_put: False in neutron_lib
# ---------------------------------------------------------------------------


def test_shared_change_is_immutable_drift():
    """Neutron rejects a PUT of ``shared``; report it as drift, not an update."""
    existing = {"network_type": "vlan", "physical_network": "physnet1", "shared": True}

    drift = reconcile._immutable_drift(existing, _spec(shared=False, project_id="p1"))

    assert drift is not None
    assert "shared" in drift


def test_project_id_change_on_unshared_range_is_immutable_drift():
    existing = {
        "network_type": "vlan",
        "physical_network": "physnet1",
        "shared": False,
        "project_id": "old-project",
    }

    drift = reconcile._immutable_drift(
        existing, _spec(shared=False, project_id="new-project")
    )

    assert drift is not None
    assert "project_id" in drift


def test_project_id_is_ignored_for_shared_range():
    """A shared range ignores project_id, so a stored value is not drift."""
    existing = {
        "network_type": "vlan",
        "physical_network": "physnet1",
        "shared": True,
        "project_id": "leftover",
    }

    assert reconcile._immutable_drift(existing, _spec(shared=True)) is None


# ---------------------------------------------------------------------------
# _mutable_updates: only minimum and maximum are PUT-able
# ---------------------------------------------------------------------------


def test_mutable_updates_reports_only_minimum_and_maximum():
    existing = {
        "minimum": 100,
        "maximum": 200,
        "shared": True,
        "project_id": None,
    }

    updates = reconcile._mutable_updates(existing, _spec(minimum=100, maximum=300))

    assert updates == {"maximum": 300}


def test_mutable_updates_ignores_shared_and_project_id():
    """shared/project_id are immutable now, so they never appear as updates."""
    existing = {"minimum": 100, "maximum": 200, "shared": True}

    updates = reconcile._mutable_updates(
        existing, _spec(minimum=100, maximum=200, shared=False, project_id="p1")
    )

    assert updates == {}
