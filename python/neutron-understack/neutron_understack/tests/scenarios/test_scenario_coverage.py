"""Validate properties of the human-readable scenario catalog.

The collection hook validates marker shape and checks the catalog against the
tests pytest actually collects. That avoids source scanning that can count a
marker in a comment or dead code as an implemented scenario.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from neutron_understack.tests.scenarios.catalog import catalog_ids
from neutron_understack.tests.scenarios.conftest import _scenario_id

SCENARIOS_DIR = Path(__file__).parent
CATALOG = SCENARIOS_DIR / "SCENARIOS.md"


def _catalog_ids():
    return catalog_ids(CATALOG.read_text())


def test_catalog_has_no_duplicate_ids():
    ids = _catalog_ids()
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not duplicates, f"duplicate scenario IDs in SCENARIOS.md: {duplicates}"


def _item_with_marker(marker):
    return SimpleNamespace(get_closest_marker=lambda _name: marker)


def test_valid_scenario_marker_returns_id():
    item = _item_with_marker(pytest.mark.scenario("BM-BIND-01").mark)
    assert _scenario_id(item) == ("BM-BIND-01", None)


@pytest.mark.parametrize(
    "marker",
    [
        None,
        pytest.mark.scenario().mark,
        pytest.mark.scenario("BM-BIND-01", "extra").mark,
        pytest.mark.scenario(id="BM-BIND-01").mark,
        pytest.mark.scenario(123).mark,
        pytest.mark.scenario("").mark,
        pytest.mark.scenario("bm-bind-01").mark,
    ],
)
def test_malformed_scenario_marker_is_rejected(marker):
    scenario_id, error = _scenario_id(_item_with_marker(marker))
    assert scenario_id is None
    assert error
