"""Scenario-test collection enforcement and JUnit tagging hooks.

- Validates every collected scenario marker and rejects unknown catalog IDs.
- When all scenario modules are collected, fails if a catalog entry has no test.
- Stamps each scenario test's ID onto ``user_properties`` so it surfaces in the
  JUnit XML as ``<property name="scenario" value="<ID>"/>``. scripts/
  scenario-report.py turns that into a scenario→status traceability matrix.
"""

from pathlib import Path

import pytest

from neutron_understack.tests.scenarios.catalog import SCENARIO_ID_RE
from neutron_understack.tests.scenarios.catalog import catalog_ids

# The catalog meta-test is not itself a scenario.
_EXEMPT_FILES = {"test_scenario_coverage.py"}
_SCENARIOS_DIR = Path(__file__).parent
_CATALOG = _SCENARIOS_DIR / "SCENARIOS.md"


def _scenario_id(item):
    marker = item.get_closest_marker("scenario")
    if marker is None:
        return None, "missing an @pytest.mark.scenario('<ID>') marker"
    if len(marker.args) != 1 or marker.kwargs:
        return None, "scenario marker must have exactly one positional ID"

    scenario_id = marker.args[0]
    if not isinstance(scenario_id, str) or not SCENARIO_ID_RE.fullmatch(scenario_id):
        return None, f"invalid scenario ID {scenario_id!r}"
    return scenario_id, None


def pytest_collection_modifyitems(config, items):
    errors = []
    collected_ids = set()
    collected_files = set()
    for item in items:
        item_path = Path(str(getattr(item, "fspath", ""))).resolve()
        path = item_path.as_posix()
        if "/tests/scenarios/" not in path:
            continue
        if item_path.name in _EXEMPT_FILES:
            continue

        collected_files.add(item_path)
        scenario_id, error = _scenario_id(item)
        if error:
            errors.append(f"{item.nodeid}: {error}")
            continue
        collected_ids.add(scenario_id)
        item.user_properties.append(("scenario", scenario_id))

    catalog = catalog_ids(_CATALOG.read_text())
    unknown = sorted(collected_ids - set(catalog))
    if unknown:
        errors.append(f"scenario IDs missing from SCENARIOS.md: {unknown}")

    scenario_files = {
        scenario_path.resolve()
        for scenario_path in _SCENARIOS_DIR.glob("test_*.py")
        if scenario_path.name not in _EXEMPT_FILES
    }
    invocation_dir = Path(config.invocation_params.dir)
    requested_paths = {
        (invocation_dir / str(arg).split("::", 1)[0]).resolve()
        for arg in config.args
        if not str(arg).startswith("-")
    }
    full_scenario_scope = any(
        _SCENARIOS_DIR.resolve().is_relative_to(requested_path)
        for requested_path in requested_paths
    )
    if full_scenario_scope or (scenario_files and scenario_files <= collected_files):
        untested = sorted(set(catalog) - collected_ids)
        if untested:
            errors.append(f"catalogued scenarios with no collected test: {untested}")

    if errors:
        raise pytest.UsageError(
            "scenario collection validation failed:\n  " + "\n  ".join(errors)
        )
