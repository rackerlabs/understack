"""Scenario-test enforcement + JUnit tagging hooks.

- Fails collection if any test under the scenarios package is missing a
  ``@pytest.mark.scenario("<ID>")`` marker, so a scenario test cannot silently
  escape the catalog↔marker coverage check in test_scenario_coverage.py.
- Stamps each scenario test's ID onto ``user_properties`` so it surfaces in the
  JUnit XML as ``<property name="scenario" value="<ID>"/>``. scripts/
  scenario-report.py turns that into a scenario→status traceability matrix.
"""

import pytest

# The coverage meta-test verifies the catalog itself and is not a scenario.
_EXEMPT_FILES = {"test_scenario_coverage.py"}


def pytest_collection_modifyitems(items):
    missing = []
    for item in items:
        path = str(getattr(item, "fspath", "")).replace("\\", "/")
        if "/tests/scenarios/" not in path:
            continue
        if path.rsplit("/", 1)[-1] in _EXEMPT_FILES:
            continue
        marker = item.get_closest_marker("scenario")
        if marker is None:
            missing.append(item.nodeid)
            continue
        if marker.args:
            item.user_properties.append(("scenario", marker.args[0]))
    if missing:
        raise pytest.UsageError(
            "scenario tests missing an @pytest.mark.scenario('<ID>') marker:\n  "
            + "\n  ".join(missing)
        )
