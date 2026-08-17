---
authors:
    - "@geetikabatra"
reviewers:
    - "@cardoe"
    - "@mfencik"
    - "@abhimanyu003"
    - "@haseebsyed12"
creation-date: 2026-07-20
last-updated: 2026-08-17
status: provisional
---

# Nautobot Resource Sync (ipsync)

## Table of Contents

- [Glossary](#glossary)
- [Summary](#summary)
- [Motivation](#motivation)
    - [Goals](#goals)
    - [Non-Goals](#non-goals)
- [Proposal](#proposal)
    - [Data Ownership: Static vs Dynamic](#data-ownership-static-vs-dynamic)
    - [User Stories](#user-stories)
    - [Requirements](#requirements)
    - [Implementation Details/Notes/Constraints](#implementation-detailsnotesconstraints)
- [Open Questions](#open-questions)
- [Alternatives Considered](#alternatives-considered)
- [Additional Details](#additional-details)
    - [Test Plan](#test-plan)
    - [Subtasks](#subtasks)
    - [Graduation Criteria](#graduation-criteria)
- [References](#references)
- [Implementation History](#implementation-history)

## Glossary

- **Nautobot** - our DCIM/IPAM system. For everything in scope here it is a
  projection rather than an origin: static data is rendered into it from the
  deploy repo, and dynamic data is recorded in it by the site event path. It is
  not an authoring surface — nothing is created there by hand and expected to
  survive. See [Data Ownership: Static vs Dynamic](#data-ownership-static-vs-dynamic).
- **nautobotop** - the Nautobot Operator we already run. It reads YAML out of
  Kubernetes ConfigMaps and pushes it into Nautobot through the Nautobot API,
  including deleting Nautobot objects that no longer appear in the YAML. It is a
  one-directional deploy-repo → Nautobot sync. See the
  [Nautobot Operator guide](../operator-guide/nautobotop.md).
- **Global cluster** - the cluster where Nautobot, the Nautobot worker, and
  nautobotop run. Sites can reach it.
- **Management cluster** - the ArgoCD and logging environment. Nautobot does
  *not* run here.
- **Site** - a physical undercloud location with its own hardware, its own
  Kubernetes cluster, and its own OpenStack services (Neutron, Ironic).
- **Deploy repo** - `RSS-Engineering/undercloud-deploy`, which holds the
  per-environment hardware YAML (for example `hardware/vlan-groups/staging/vlan-groups.yaml`)
  that gets rendered into the ConfigMaps nautobotop consumes.
- **Static generator** - the generator producing per-site data
  (OOB IP ranges, VNI ranges, BGP ASNs, switch loopback IPs) as a file committed
  to the deploy repo for nautobotop to consume. Being built separately.
- **Static data** - data authored up front, by design or by the static generator,
  in the deploy repo. Git is the source of truth: the deploy repo file is where
  changes are made and where people look values up.
- **Dynamic data** - values a site's own OpenStack services produce at runtime,
  inside the ranges the deploy repo authored. Nautobot's copy of them is a
  recorded reading of what a site currently has — useful for visibility and drift
  reporting, never authoritative, and never something to author against.
- **ipsync** - the work described in this proposal: making the deploy repo the
  single authoring surface for Nautobot, validating what it contains before it
  reaches Nautobot, keeping dynamic data distinguishable from static data, and
  reading actual state back from each site.

## Summary

The deploy repo is the source of truth for Nautobot. Hardware YAML in
`RSS-Engineering/undercloud-deploy` — for example
`hardware/vlan-groups/staging/vlan-groups.yaml` — together with the static
generator's output committed alongside it, is where every resource type in scope
is authored: VLAN group ranges, locations, racks, device types, OOB IP ranges, VNI
ranges per site, BGP ASNs, switch loopback IPs. Changes are made there, reviewed
there, and looked up there. Nautobot holds a copy rendered from it, and nautobotop
is the mechanism that renders it.

Nautobot also has to hold one more thing: what sites actually have. Tenant VLANs,
VNIs and subnets come into existence when a tenant calls a site's Neutron API,
inside the ranges the deploy repo authored, and they reach Nautobot through the
existing event path. This proposal keeps that path but fixes its standing: what it
writes is a recorded reading of the site, for visibility and drift reporting. It
is not authoritative, and nothing is ever authored from it.

This proposal does three things:

1. States the deploy repo as the single authoring surface, and records per
   resource type whether Nautobot's copy is static (rendered from the deploy repo)
   or dynamic (recorded from a site).
2. Makes that enforceable in nautobotop rather than a convention we rely on. As
   things stand its delete pass walks every object of a type and removes what is
   not in the YAML, which would take dynamic objects with it, so the pass needs to
   know which objects it rendered.
3. Scopes the first increment of work: full CRUD for **VLAN Groups** driven from
   the deploy repo YAML, with validation of that YAML, plus a **pull-based**
   read-back of actual state from a site so we can report drift.

Earlier drafts of this proposal described a generic two-way sync with a
`spec`/`status` split and writeback into Nautobot for any resource type. We've
stepped back from that: writeback treats a reading as authoritative, which tends
to invite sync loops and lets Nautobot's copy drift away from the file people are
reading. Static data flows one way, deploy repo → Nautobot. Dynamic data flows the
other, site → Nautobot, report only. The two never meet in the same field.

This work doesn't rely on Cluster API or its IPAM claim/pool contract.

## Motivation

### Nothing distinguishes what we authored from what a site reported

nautobotop reconciles by listing everything of a given type in Nautobot and
deleting whatever is not in the YAML. For VLANs that is
[`deleteObsoleteVlans`](https://github.com/rackerlabs/understack/blob/main/go/nautobotop/internal/nautobot/sync/vlan.go),
which calls `ListAll` and removes every VLAN whose name is absent from the
ConfigMap; VLAN groups, racks, devices, prefixes and the rest follow the same
shape. Meanwhile, dynamic VLANs created in a site's Neutron already reach
Nautobot through the existing oslo notification → Argo Events → Argo Workflows →
`ironic-nautobot-client` path.

Those two facts together mean that as soon as site-reported VLANs land in
Nautobot, a nautobotop reconcile deletes them, because they were never in the
deploy repo YAML. The delete pass is right to remove anything absent from the
deploy repo *among the objects it rendered* — that is what makes git the source of
truth — but it currently cannot tell those apart from readings the event path
recorded. So the marking has to be explicit at the object level.

### Static data reaches Nautobot unvalidated

References in the YAML are resolved by name at reconcile time, and a name that
does not resolve is silently dropped rather than rejected. In
[`vlanGroup.go`](https://github.com/rackerlabs/understack/blob/main/go/nautobotop/internal/nautobot/sync/vlanGroup.go),
`buildLocationReference` returns an empty reference when the location lookup
fails, so a VLAN group with a mistyped `location` is created in Nautobot with no
location at all and no error surfaced. A typo in the deploy repo becomes bad
data in Nautobot, discovered later by whoever depends on it. Since the deploy repo
is also where people look values up, the file and Nautobot end up disagreeing with
nothing to signal it.

### There is no way to ask a site what is actually configured

Nautobot holds the authored intent and a copy of some runtime values, but nothing
reads a site back to confirm the two agree. Drift is found by hand.

### Ansible-driven sync does not cover deletion

The existing Ansible-based flows can create and update, but deletion is the hard
case: nothing tracks what was previously applied, so removing an entry from the
YAML does not remove it from the target. An operator with a level-triggered
reconcile loop does handle this, and also gives us per-site conditions, metrics,
and observability that a one-shot playbook does not.

### Goals

1. Establish the deploy repo as the single authoring surface for Nautobot, and
   document the static/dynamic classification per resource type we intend to sync.
2. Keep nautobotop strictly one-directional (deploy repo YAML → Nautobot) and
   strictly limited to static data. nautobotop never writes to Neutron, Ironic,
   or any site.
3. Make nautobotop's delete pass ownership-scoped, so it cannot delete objects it
   did not render, regardless of what else lives in Nautobot.
4. Validate the deploy repo YAML — structurally and referentially — and fail
   loudly with an actionable message instead of writing partial data.
5. Provide a pull-based way to read actual state from a site into the global
   cluster, and report disagreement between that and Nautobot.
6. Deliver this end to end for one resource type first (VLAN Groups, then
   VLANs), in a shape that generalizes to the other types without redesign.

### Non-Goals

1. **No two-way sync.** No field is written from both directions, and no value a
   site reported is ever promoted into static data by a machine. nautobotop does
   not write individual VLANs, VNIs, or tenant subnets, since those are allocated
   at runtime rather than authored.
2. **No automatic conflict resolution.** When actual state and Nautobot
   disagree, ipsync reports it. Deciding what to do is a human call for now, and
   for static data the fix is an edit to the deploy repo.
3. **Not new-site onboarding.** Bringing a new cab or site online is covered by
   [ADR027](https://docs.undercloud.rackspace.net/architecture-decisions/adr027-automated-cab-addition/).
4. **Not a replacement for the existing dynamic path.** The oslo notification →
   Argo Events → Argo Workflows → `ironic-nautobot-client` route stays as the way
   dynamic data reaches Nautobot. ipsync makes what it writes distinguishable as a
   reading rather than authoritative data; it does not duplicate the path.
5. **No Cluster API**, no IPAM provider pattern, no claim/pool contract.
6. **Not deciding the static generator's output format.** That is being designed
   separately; this proposal only states that nautobotop consumes it as static
   data.

## Proposal

### Data Ownership: Static vs Dynamic

The deploy repo is the source of truth throughout. The classification below is
about what each row *is* in Nautobot — data rendered from the deploy repo, or a
reading recorded from a site — and therefore who may write it. This table is the
part of the proposal that most needs agreement; everything else follows from it.

| Data | Authored in | Class | Direction | Mechanism |
|------|-------------|-------|-----------|-----------|
| VLAN groups (name, location, range) | Deploy repo YAML | static | deploy repo → Nautobot | nautobotop |
| Locations, location types, racks, rack groups | Deploy repo YAML | static | deploy repo → Nautobot | nautobotop |
| Device types | Deploy repo YAML | static | deploy repo → Nautobot | nautobotop |
| VLAN ID / VNI / subnet ranges a site may allocate from | Deploy repo YAML or generator | static | deploy repo → Nautobot | nautobotop |
| OOB IP ranges | Static generator, committed to deploy repo | static | generator file → Nautobot | nautobotop |
| VNI ranges per site | Static generator, committed to deploy repo | static | generator file → Nautobot | nautobotop |
| BGP ASNs | Static generator, committed to deploy repo | static | generator file → Nautobot | nautobotop |
| Switch loopback IPs | Static generator, committed to deploy repo | static | generator file → Nautobot | nautobotop |
| Tenant VLAN / VNI / subnet allocations | Not authored — allocated at runtime by a site's Neutron, inside the authored ranges | dynamic | site → Nautobot, report only | existing oslo/Argo path |
| Device/port actual state | Not authored — reported by site Ironic | dynamic | site → global, report only | ipsync read-back |

Four rules fall out of it:

- Every object in Nautobot is either rendered from the deploy repo or recorded as
  a reading from a site. There is no third category, and nothing in Nautobot is
  authoritative on its own.
- nautobotop may create, update, and delete only rows marked **static**, and only
  the objects it rendered.
- For rows marked **dynamic**, nautobotop must not create, update, or delete —
  including via its delete-obsolete pass. Nautobot's copy of that data is a
  reflection of the site, not an instruction to it.
- A dynamic value is never promoted into static data by a machine. If a site has
  something the deploy repo does not, that is drift to report, and a human
  resolves it by editing the deploy repo.

Rows will be added as more types come into scope. Anything not classified is out
of scope until it is.

### User Stories

#### Story 1 - A typo in the deploy repo is caught before it reaches Nautobot

Someone edits `hardware/vlan-groups/staging/vlan-groups.yaml` and misspells the
location. Today the VLAN group is created in Nautobot with no location and no
complaint. With ipsync, validation rejects the entry, the reconcile reports the
failure on the `Nautobot` CR status and in metrics, and Nautobot is left
unchanged.

#### Story 2 - A VLAN group is removed from the deploy repo

The entry is deleted from the YAML, and nautobotop deletes the corresponding
VLAN group in Nautobot — but only because that object is marked as nautobotop
owned. Nothing else in Nautobot is affected.

#### Story 3 - A tenant VLAN is created at a site

Neutron at the site allocates a VLAN from the range the deploy repo authored. It
reaches Nautobot through the existing event path and is recorded there as a
reading. nautobotop sees an object it did not render, leaves it alone, and never
deletes it, even though it is not in any deploy repo YAML. If the allocation falls
outside the authored range, that is drift and gets reported.

#### Story 4 - Someone asks whether a site matches Nautobot

ipsync pulls actual state for the resource type from the site, compares it with
Nautobot, and reports the differences with enough detail to act on. It does not
change either side.

#### Story 5 - Someone needs to change a VLAN group range

They edit the deploy repo YAML, open a review, and merge. Validation runs in CI
before the merge, nautobotop renders the change into Nautobot on the next
reconcile, and the file remains the thing to read to find out what the range is.
Editing the same value directly in Nautobot is not a supported route: the next
reconcile puts it back to what the file says.

### Requirements

#### Functional Requirements

- **FR1**: nautobotop keeps its current direction of travel: ConfigMap YAML from
  the deploy repo into Nautobot. That does not change. The deploy repo is the only
  authoring surface for static data, so an edit made directly in Nautobot to a
  static type is not preserved across a reconcile.
- **FR2**: Objects nautobotop creates in Nautobot are marked as nautobotop
  owned, using a mechanism Nautobot can filter on (see
  [Open Questions](#open-questions) for which one).
- **FR3**: Every delete-obsolete pass is scoped to objects carrying that
  ownership marker. An unmarked object is never deleted.
- **FR4**: The YAML is validated before any write to Nautobot:
    - structurally, against a schema (required fields, VLAN ID and range bounds,
      duplicate names);
    - referentially, against the Nautobot API (does this location exist?).
- **FR5**: A validation failure fails the reconcile for that resource with a
  named error, surfaces it on the CR status, and does not write partial data. A
  reference that cannot be resolved is never silently dropped.
- **FR6**: ipsync can pull actual state for a resource type from a site and
  compare it against Nautobot.
- **FR7**: Differences are reported (CR status conditions, logs, metrics). No
  automatic remediation, and no writing a reported value back as static data.
- **FR8**: The first increment covers VLAN Groups end to end — create, update,
  delete, validate, read back — followed by VLANs.
- **FR9**: Site interaction uses the OpenStack APIs (Neutron, Ironic) directly
  rather than shelling out to the OpenStack CLI.
- **FR10**: Dynamic data written by the event path is distinguishable in Nautobot
  from static data, so "what did we author?" and "what does the site actually
  have?" are separately answerable.

#### Non-Functional Requirements

- **NFR1**: Unit tests for the ownership-scoped delete pass, including the case
  where Nautobot contains unmarked objects of the same type.
- **NFR2**: Unit tests for schema validation and for referential validation,
  covering the unresolved-location case that currently fails silently.
- **NFR3**: Reconciles stay idempotent — an unchanged YAML produces no Nautobot
  writes and no change-log noise.
- **NFR4**: Per-site, per-resource metrics: reconcile outcome, validation
  failures, objects created/updated/deleted, drift count, last successful pull.
- **NFR5**: A site being unreachable is a reported condition, not a failed
  reconcile of unrelated resources.

### Implementation Details/Notes/Constraints

#### Current State

- nautobotop runs on the **global cluster** (`global.nautobotop` in the deploy
  repo) and pushes ConfigMap YAML into Nautobot. It supports location types,
  locations, rack groups, racks, device types, VLAN groups, VLANs, prefixes,
  namespaces, RIRs, roles, tenants, tenant groups, clusters, cluster types, and
  cluster groups.
- Its delete pass is unscoped: list everything of a type, delete what is not in
  the YAML.
- Reference resolution is by name with silent failure on miss.
- Dynamic data flows site → Nautobot today via oslo notifications, captured by
  Argo Events, handled by Argo Workflows, with `ironic-nautobot-client` making
  the Nautobot calls. A Nautobot worker driven from global runs the jobs. This
  replaced an earlier ServiceNow-based job.
- Sites can reach the global cluster. Whether the global cluster can reach a
  site's OpenStack APIs is not yet confirmed.
- There is no validation layer and no read-back of actual state.

#### Ownership Marking

The delete pass needs a filter it can trust. Every object nautobotop writes gets
a marker — a tag, a custom field, or a relationship — and `deleteObsolete*`
switches from "list all of this type" to "list all of this type carrying the
marker". Consequences:

- Site-reported objects are structurally invisible to the delete pass.
- Existing objects that nautobotop created before this change are unmarked, so a
  one-time backfill is needed before the scoped delete can be trusted to remove
  anything. Until the backfill runs, the scoped pass simply deletes less than
  today, which is the safe direction.
- The marker also gives us a cheap answer to "did we author this, or did a site
  report it?" when reporting drift.

#### Validation

Two layers, because they catch different mistakes:

1. **Schema validation** of the deploy repo YAML. Catches shape errors and can
   run in the deploy repo's own CI, before merge, where the feedback is most
   useful. Also runs in nautobotop so a hand-edited ConfigMap cannot bypass it.
2. **Referential validation** against the Nautobot API at reconcile time.
   Catches a well-formed file that refers to something that does not exist —
   the mistyped location case. This is the direct API call approach suggested on
   the sync-up call, and it is the only layer that can see Nautobot's actual
   contents.

Nautobot also has its own server-side data validation mechanism. That is worth
using as a backstop for anything that must hold regardless of which client
writes it, but it cannot replace layer 1 (too late, and the error surfaces in the
wrong place) — see [Open Questions](#open-questions).

Validation failures are reported per entry, not as a single opaque reconcile
error, so a bad line in a large file names itself.

#### Reading Actual State Back From a Site

The agreed preference is a **pull** model: the global cluster asks, the site
answers. Pull keeps credentials and scheduling on one side, makes "when did we
last look?" answerable, and avoids every site needing write access to global
state.

Two shapes, depending on reachability:

- **Global → site OpenStack APIs directly.** A controller on the global cluster
  holds per-site credentials and queries Neutron/Ironic. Nothing new to deploy
  per site. Requires the global cluster to reach site API endpoints.
- **Per-site agent, pulled by global.** A small read-only agent at each site
  exposes the data; global pulls it on a schedule. Works when site APIs are not
  directly reachable, at the cost of a component per site.

Sites can reach the global cluster, so a site-initiated push is technically
available as a fallback. It is not preferred: it inverts control of scheduling
and needs write credentials at every site.

Read-back is read-only in both shapes. It never writes to the site, and it does
not write dynamic data into Nautobot — that remains the existing event path's
job. Its output is a comparison report, and a difference it finds in a static type
is fixed by editing the deploy repo, not by writing to either side.

#### Why an Operator

A Kubernetes operator gives us the deletion semantics Ansible lacks, a
level-triggered reconcile that converges after transient failures, per-site
status conditions, and metrics. It is also where we already are: nautobotop
exists, runs on global, and owns the write path into Nautobot.

#### First Increment

VLAN Groups, end to end, as the concrete slice:

1. Ownership marker written on create, delete pass scoped to it, with tests.
2. Schema validation for `vlan-groups.yaml`, plus referential validation of
   `location` against Nautobot, replacing the silent empty-reference path.
3. Validation and reconcile results reported on the CR status and as metrics.
4. Read-back of VLAN group state from one site, and a drift report.
5. Repeat for VLANs, which is where the static/dynamic boundary actually bites,
   since Nautobot holds both VLANs rendered from the deploy repo and VLANs
   reported from a site's Neutron.

## Open Questions

1. **Do tenant allocations need to be authored in the deploy repo at all?** This
   proposal says the deploy repo authors the *ranges*, and the individual tenant
   VLAN, VNI and subnet allocations inside those ranges are runtime values that
   Nautobot merely records. The stricter reading — every VLAN declared in git
   before a tenant can use it — would mean giving up tenant self-service network
   creation, since a tenant API call cannot wait on a merge. This needs agreement
   before VLANs are implemented, because it decides whether the event path stays.
2. **What should happen to a hand edit made directly in Nautobot** to a static
   type? As specified it is reverted on the next reconcile, silently. Reverting is
   right, but it may be worth reporting rather than doing quietly, so the person
   who made the edit finds out.
3. **Which Nautobot mechanism marks ownership** — tag, custom field, or
   relationship — and how do we backfill objects nautobotop already created?
2. **Can the global cluster reach site Neutron/Ironic APIs?** Sites reaching
   global is confirmed; this direction is not, and it decides whether we need a
   per-site agent.
3. **Where does validation live?** Deploy repo CI, nautobotop, Nautobot's
   server-side validators, or some split across all three.
4. **What does the static generator emit, and how does it reach nautobotop?**
   A file committed to the deploy repo and rendered into a ConfigMap is the
   assumption here; it needs confirming against that work.
5. **How are per-environment VLAN group files (`staging/`, production) rendered
   into ConfigMaps**, and does each environment get its own `Nautobot` CR?
6. **Which resource types come after VLANs**, and does each need its own
   classification review before it is added to the table?

## Alternatives Considered

- **Generic two-way sync with a `spec`/`status` split and writeback into
  Nautobot** (the original version of this proposal). Rejected: it treats a
  reading of a site as authoritative, which risks sync loops and lets Nautobot's
  copy drift away from the deploy repo file people are reading. With the deploy
  repo as the source of truth, one-directional sync per type is sufficient and
  much less machinery.
- **Cluster API's IPAM provider pattern (`IPAddressClaim`/`IPAddress`)**.
  Rejected: no machine lifecycle here, and it adds a contract we would only be
  borrowing vocabulary from.
- **Convention-based static/dynamic separation** (agree not to put dynamic data
  in the same Nautobot tables, leave the delete pass as is). Rejected: the
  existing event path already writes dynamic VLANs into Nautobot, so the
  convention is already broken and the failure mode is silent deletion.
- **Authoring everything in the deploy repo, including individual tenant VLANs and
  subnets.** This is the cleanest form of "git is the source of truth" and is why
  the ranges are authored there. Not adopted for the individual allocations
  themselves: a tenant creating a network calls Neutron and gets an answer
  immediately, which no git-mediated flow can supply. Recorded as
  [Open Question 1](#open-questions) rather than settled here.
- **Ansible-driven sync**. Rejected as the primary mechanism: no deletion
  semantics, no drift detection, no metrics. Still fine for one-shot tasks
  outside this scope.
- **Site-initiated push to the global cluster**. Kept as a fallback if pull turns
  out to be impractical, but not preferred — it needs write credentials per site
  and moves scheduling to the sites.
- **Wrapping the OpenStack CLI at the site**. Rejected: subprocess management and
  output parsing, where the APIs give structured responses and real errors.

## Additional Details

### Test Plan

- Unit tests: delete pass with a mix of marked and unmarked objects of the same
  type; assert unmarked objects survive.
- Unit tests: schema validation rejects missing required fields, out-of-range
  VLAN IDs, malformed ranges, and duplicate names, per entry.
- Unit tests: referential validation fails on an unresolvable location instead of
  writing an object with an empty reference.
- Unit tests: unchanged YAML produces no Nautobot writes.
- Integration tests against a test Nautobot instance: create, update, and scoped
  delete for VLAN Groups, including a pre-existing unmarked object.
- Integration test: a site-reported VLAN present in Nautobot survives a full
  nautobotop reconcile.
- End-to-end: pull VLAN group state from a site, report drift against Nautobot,
  including one deliberate mismatch, and assert neither side is modified.

### Subtasks

- [ ] Agree the static/dynamic table, including which types are in scope now, and
      settle whether tenant allocations are authored or only recorded
      ([Open Question 1](#open-questions)).
- [ ] Decide the ownership marker and write the backfill for existing objects.
- [ ] Scope every `deleteObsolete*` pass to the marker.
- [ ] Add schema validation for `vlan-groups.yaml`, wired into deploy repo CI and
      nautobotop.
- [ ] Add referential validation against the Nautobot API; remove the silent
      empty-reference path in `buildLocationReference` and its equivalents.
- [ ] Surface validation and reconcile results on the `Nautobot` CR status and as
      metrics.
- [ ] Confirm whether the global cluster can reach site Neutron/Ironic APIs.
- [ ] Build the pull-based read-back for VLAN Groups against one site.
- [ ] Extend to VLANs, including the mixed static/dynamic case.
- [ ] Confirm the static generator's output format and ingestion path.

### Graduation Criteria

#### Alpha

- Static/dynamic table agreed and merged.
- Ownership marker written and delete passes scoped, with tests proving unmarked
  objects are never deleted.
- VLAN Group schema and referential validation in place, failures visible on the
  CR status.

#### Beta

- Pull-based read-back working for VLAN Groups against at least one real site,
  with a drift report.
- VLANs supported, with a test proving site-reported VLANs survive reconciles.
- Metrics exported per site and per resource type.

#### Stable

- Running across multiple sites through several reconcile cycles with no
  unintended deletions and no data loss.
- Every resource type nautobotop syncs is classified in the table.
- No supported workflow requires editing a static value anywhere but the deploy
  repo.

## References

- [Nautobot Operator guide](../operator-guide/nautobotop.md)
- [nautobotop component deployment](../deploy-guide/components/nautobotop.md)
- [ADR027 - automated cab addition](https://docs.undercloud.rackspace.net/architecture-decisions/adr027-automated-cab-addition/)
- [`hardware/vlan-groups/staging/vlan-groups.yaml`](https://github.com/RSS-Engineering/undercloud-deploy/blob/main/hardware/vlan-groups/staging/vlan-groups.yaml)
- [Argo Events design guide](../design-guide/argo-events.md)
- [OpenStack/Nautobot sync](../operator-guide/openstack-nautobot-sync.md)

## Implementation History

- 2026-07-20: Initial draft, from design discussion with Abhimanyu Sharma and
  Syed Haseeb Ahmed.
- 2026-07-20: Dropped the full two-way sync alternative because of possible sync
  loops.
- 2026-07-22: Review feedback. Nautobot and nautobotop run on the **global**
  cluster, not the management cluster, and sites can reach global (@cardoe).
  Nautobot is not the source of truth for dynamic data — each site's Neutron owns
  VLANs, VNIs, and tenant subnets; nautobotop was meant for static data from the
  static generator; the split needs deciding first (@mfencik, ADR027).
- 2026-07-27: Sync-up call. Focus on VLAN Groups from the deploy repo YAML first;
  deploy repo YAML stays the source of truth; validation is needed and can call
  the Nautobot API directly (@abhimanyu003); Ansible cannot handle deletion
  (@haseebsyed12); pull from the site is preferred; start with full CRUD for one
  resource.
- 2026-08-13: Rewritten around the static/dynamic ownership split, generic
  two-way sync and Nautobot writeback withdrawn, site reachability question
  replaced with the global-cluster facts, first increment scoped to VLAN Groups.
  Moved into the new `docs/proposals/` section.
- 2026-08-17: Stated the deploy repo as the source of truth for Nautobot outright:
  Nautobot is a projection, not an authoring surface, and dynamic data in it is a
  recorded reading rather than an authoritative copy owned by a site. Added the
  authored allocation ranges to the ownership table, the rule that a dynamic value
  is never promoted to static by a machine, Story 5 for the edit-the-file
  workflow, FR10, and open questions on tenant allocations and hand edits made in
  Nautobot.
