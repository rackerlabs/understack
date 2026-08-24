# ML2 mechanism scenario catalog

This is the human-readable **test plan** for the `neutron-understack` ML2 mechanism
drivers. Each scenario is given a stable ID and describes the operation it models
and the **mechanism calls + data** we expect to observe.

Every scenario here must be implemented by at least one test tagged
`@pytest.mark.scenario("<ID>")`, and every such marker must reference a scenario
that exists here. `test_scenario_coverage.py` enforces this equivalence in both
directions, and `conftest.py` fails the run if any scenario test is missing a
marker. So this file and the tests cannot silently drift apart.

## Conventions

- Scenario IDs are declared as `### <ID> — <title>` headings, e.g.
  `### BM-BIND-01 — baremetal vif-attach binds hierarchically`. IDs use the form
  `<AREA>-<TOPIC>-<NN>` (uppercase, hyphenated), which the coverage check parses.
- Ideas not yet implemented go under a "Planned / future" section as plain bullets
  (no `###` heading) so they are not treated as catalogued-but-untested.
- A scenario whose desired behavior is a known bug is still catalogued; its test
  asserts the desired behavior and is marked `@pytest.mark.xfail(strict=True)` with
  a reason. Record such bugs under a "Known bugs" section.

Scenarios are added per driver/area (baremetal port binding, routers, trunks, ...)
as those test modules land.
