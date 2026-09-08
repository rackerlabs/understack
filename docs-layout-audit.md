# Documentation Layout Audit

**Status:** Phase 1 has landed; Phases 2–6 are a proposal, for team review. This
file is a planning artifact, not product documentation. Delete it once the phases
below have landed or been rejected.

It lives at the repository root rather than under `docs/` on purpose: every file
under `docs/` has to be added to `nav:` in `properdocs.yml` and gets published to
the site, and this is not something a reader of the docs site should ever find.

## Why

Does the current documentation layout serve the audiences the project has?

- **system operators** deploying and troubleshooting the whole system,
- **DC techs** working with individual machines,
- **network operations** working with network configuration,
- **users** consuming the cloud (tenants driving the OpenStack APIs and CLI),
- **contributors** changing the code.

Short answer: the layout has drifted in specific, fixable ways, and it fronts
none of these five audiences well. Contributors have no entry point at all.
Users have a thin `User Guide`, but its consumer readers are not who the
surrounding operator docs address. And the three operator roles share a single
undifferentiated `Operator Guide`: it does not distinguish deploying and
troubleshooting the whole system from working on individual machines from
configuring the network — it hands all three the same flat page list.

## What is there now

The counts and structure in this section describe the layout **as it was before
Phase 1**, because that is what the findings below are about. Phase 1 has since
changed the tabs and added five pages; it moved nothing, so every finding still
points at a real file. Current state is 141 pages under seven tabs.

137 markdown pages, all of them listed in the hand-maintained `nav:`. Eight
top-level entries: `Home`, `Overview`, `Design Guide`, `Deployment Guide`,
`Operator Guide`, `Release Notes`, `User Guide`, `Workflows`.

Three things are generated at build time — `docs/workflows/` from
`scripts/argo-workflows-to-mkdocs.py`, the neutron sample config from
`oslo-config-generator`, and `docs/release-notes/unreleased.md` from the
`changelog.d/` fragments via `make unreleased-notes` (scriv) — and 56 of the 137
are component reference pages under `docs/deploy-guide/components/`.

Separately, **61 markdown files live outside `docs/`** and are invisible to the
site. Several are substantial: `go/ironic-hardware-exporter/README.md` (436
lines), `python/understack-tests/README.md` (379),
`charts/argocd-understack/README.md` (268), `go/dexop/README.md` (231),
`RELEASING.md` (167), `ansible/README.md` (162). There is also a third docs tree
at `workflows/argo-events/docs/`.

## Findings

### The big one: no contributor documentation exists

There was no contributor section on the site, and there is still no
`CONTRIBUTING.md` in the repository. Phase 1 added a `Contributing` front door,
but a front door is not documentation: everything a new developer actually needs
is still in those 61 external files, which are unlinked, unlinted for links, and
drifting. Phase 6 is where that gets fixed. The clearest symptom is three
near-identical `DEVELOPMENT.md` files (`python/ironic-understack/`,
`python/neutron-understack/`, `python/understack-workflows/`) that differ by a
handful of lines — the classic copy-paste decay.

The release-notes work (#2191) has since added a 167-line root `RELEASING.md`
that documents the fragment workflow, the tagging process and the CI gate. It is
squarely contributor documentation, it is the one external file that is actually
current, and it is still invisible to the site — a new contributor only finds it
because `.github/pull_request_template.md` and the CI failure message point at
it. It makes the case for the Contributing tab rather than weakening it: the
process is now written down, just not anywhere a reader browses.

Meanwhile `go/nautobotop/README.md` is still unmodified kubebuilder scaffolding:
its H1 is `# rax` and it contains three `TODO(user)` placeholders, while
`docs/operator-guide/nautobotop.md` is a real 772-line document.

### `Overview` is a grab-bag, not an overview

It currently holds the vision statement, Helm/Kustomize/Kubeseal **install
instructions** (`kubernetes.md`), a 23-line `secrets.md` covering only the
MariaDB and RabbitMQ password naming convention, a 57-line `networking.md`, and
five thin `component-*.md` blurbs. A newcomer reading it end-to-end learns
very little; an operator finds install steps filed under "overview".

`component-overview.md` is also factually stale. It tells you to edit
`apps/appset/infra.yaml`, `apps/appset/operators.yaml` and
`apps/appset/components.yaml` — none of which exist. `apps/appsets/` now contains
only `argocd/` and three `project-*.yaml` files; components moved to
`charts/argocd-understack/templates/`. It also names
`scripts/gitopts-secrets-gen.sh`; the real file is `gitops-secrets-gen.sh`.

### `Design Guide` is misnamed

It mixes three audiences: hardware **schema reference** (`device-types.md`,
`hardware-traits.md`, `flavors.md`), an architecture overview, a generated oslo
config dump, and `add-remove-app.md`, which is a contributor how-to (and carries
the same staleness as `component-overview.md`). Its front door, `intro.md`, is
three lines.

### Duplication that costs readers

- **Argo Workflows is explained three times**: `docs/component-argo-workflows.md`,
  `docs/design-guide/argo-workflows.md`, `docs/operator-guide/workflows.md`.
- **OpenStack Helm three times**, two of them sharing the H1 "OpenStack Helm":
  `docs/openstack-helm.md`, `docs/deploy-guide/components/openstack-helm.md`,
  `docs/operator-guide/troubleshooting-osh.md`.
- **`server-firmware-update.md` exists twice** — in `operator-guide/` and
  `user-guide/` — with the same filename and the same H1, so they are
  indistinguishable in search results.
- `design-guide/{device-types,flavors}.md` vs `operator-guide/{device-types,flavors}.md`
  is a **correct** reference-versus-how-to split that is merely undiscoverable.
  The operator pages link to the design pages; neither design page links back.

### `networking.md` versus `neutron-networking.md`

These are different topics that share a word, and the name collision is the
actual problem. `docs/networking.md` (57 lines) is about MetalLB for DHCP and
dnsmasq tags — provisioning network plumbing. `design-guide/neutron-networking.md`
(608 lines, the largest doc in the repo) is the tenant networking model. The
short one is the nav entry point under "Configuration", so readers find the wrong
one first.

### Troubleshooting has no entry point

It is spread across `deploy-guide/troubleshooting.md` (16 lines, exactly **one**
failure mode), `operator-guide/troubleshooting-osh.md`, `operator-guide/ovs-ovn.md`,
`operator-guide/kubectl-us-net.md` and `operator-guide/logging.md`. Nothing ties
them together, so there is nowhere to land from a pager.

### Operator Guide grouping

32 pages under `OpenStack` / `Networking` / `Infrastructure` / `Hardware` /
`Scripts and Tools`, where `Infrastructure` holds 17 unrelated pages — databases,
ingress, Nautobot, logging, monitoring, Ansible. It is a dumping ground.

None of this maps to who actually reads it. System operators troubleshooting
the whole deployment, DC techs working a single machine, and network operations
configuring the network are all handed the same 32-page flat list, with nothing
marking which pages are theirs.

### Stale or unfinished content

- `deploy-guide/config-dex.md` (15 lines) instructs adding
  `nginx.ingress.kubernetes.io/proxy-redirect-*` annotations, while
  `operator-guide/gateway-api.md` documents the migration off ingress-nginx to
  Envoy Gateway. This page is in the Quick Start path, so new deployers hit it
  early. Both `docs/release-notes/index.md` and `v0.4.md` now cite
  `gateway-api.md` as *the* upgrade path off ingress-nginx, which makes the
  contradiction more visible, not less.
- `deploy-guide/components/ingress-nginx.md` still exists as an enabled-component
  page; `bootstrap/README.md` also still lists `ingress-nginx` as a bootstrap
  component, and lists only three of the four directories that are actually
  there.
- `README.md` tells you to run `nix-shell`. There is no `shell.nix` or
  `flake.nix` in the repository.
- `operator-guide/argocd-helm-chart.md` shows `understack_ref: v1.0.0  # Pin to
  specific version`, in four places. There is no `v1.x` series; the newest tag is
  `v0.4.28`. `docs/release-notes/index.md` now documents the same "pin a version"
  step with a real tag (`understack_ref: v0.4.26`) and links to
  `argocd-helm-chart.md` for the full explanation, so a reader following that
  link lands on the fictional example.
- Placeholders shipped in published prose: `operator-guide/openstack-ironic.md:14`
  reads `see [TODO: Hardware Enrollment Documentation]`;
  `deploy-guide/gitops-install.md:39` has an inline `(TODO: this defines the
  cluster)`; `user-guide/openstack-cli.md:15` has `# TODO: install
  keystoneauth-websso` inside a copy-pasteable install snippet.
- `deploy-guide/global-cluster.md:77` and `deploy-guide/site-cluster.md:80`
  contain the **identical** `!!! note "TODO"` admonition about cluster
  registration being a work in progress. Both are on the primary deployment path.

### Stubs acting as section front doors

`design-guide/intro.md` (3 lines), `user-guide/index.md` (8 lines, forwards
to upstream OpenStack docs), `operator-guide/openstack-placement.md` (17 lines,
two commands), `operator-guide/rook-ceph.md` (24 lines, dashboard access only for
a storage backend).

Phase 1 dealt with the first two: `design-guide/intro.md` is deleted (redirected
to `contributing/`) and `user-guide/index.md` is a real front door. The two
`operator-guide` stubs are still stubs — they are thin because the underlying
material is thin, which is a writing problem rather than a layout one.

### The component pages

56 of them plus an index. Roughly 27 are 45–51 line near-identical template
output; `nautobot-worker.md` is 762 lines, about 30x the median. They are
machine-shaped reference material sitting inside the install narrative.

The hand-maintained table in `deploy-guide/components/index.md` is already
visibly rotting. It has 55 rows for 56 pages: `nautobot-worker` has never been
listed, so the single largest component page is unreachable from the index that
exists to reach them. The ten OpenStack services are also appended out of
alphabetical order. Note that `scripts/check-component-docs.py` does not look at
this table at all — it only compares template names to filenames — so nothing
catches the omission.

### Build and CI hygiene

- `docs/overrides/assets/stylesheets/custom.f7ec4df2.min.css` and its `.map` are
  committed, content-hashed **build output**, referenced by nothing —
  `extra_css` points only at `stylesheets/rackspace-theme.css`, and no
  `theme.custom_dir` is configured. They are the only files in
  `docs/overrides/`.
- `requirements-docs.txt` installs three mkdocs plugins that are not enabled in
  `plugins:` and are unused: `mkdocs-swagger-ui-tag`, `mkdocs-glightbox`,
  `mkdocs-multirepo-plugin`. (`scriv`, added by #2191, is not one of these — it
  is not a plugin and the `unreleased-notes` target calls it.)
- `docs/assets/mermaid.min.js` is 2.75 MB vendored into the repository.
- `Makefile:26`'s `WFTMPLS := $(wildcard components/*-workflows/*/workflowtemplates/*.yaml)`
  matches **zero** files. The 15 real templates are in
  `workflows/argo-events/workflowtemplates/`. The target is `.PHONY` so the build
  still works, but the dependency tracking is vestigial.
- `scripts/check-component-docs.py` is one-directional: a deleted
  `application-*.yaml` leaves its docs page behind forever. It also has a real
  hole — `application-openstack-helm.yaml` is a
  `{{- range $appName := list "keystone" ... "skyline" }}` producing **ten**
  components from one template, so the script only requires
  `openstack-helm.md`. Adding an eleventh OpenStack service needs no docs page.

## Proposed layout

Seven tabs. `Home` is a router and `Reference` is cross-cutting lookup; the other
five map onto the five audiences, with system operators spanning `Deploy`
(day 0), `Operations` (day 2) and `Release Notes` (upgrades). There is
deliberately no "Introduction" tab: with no evaluator audience left to sit and
read one end-to-end, the short "what this is / how it is shaped" overview belongs
on `Home`, and the architecture depth a system operator actually needs belongs in
`Operations`, next to the troubleshooting it supports.

| Tab | Audience | Why |
| --- | --- | --- |
| **Home** | router | Already has `hide: [navigation, toc]` and a card grid. Becomes an explicit router across the five audiences, and carries the short project overview. |
| **Deploy** | system operators, day 0 | A linear install narrative with a beginning and an end. |
| **Operations** | system operators, DC techs, network operations, day 2 | The runbook library you land in from a pager, reorganized into role-aligned nav groups instead of one flat list — this is the fix for "Operator Guide grouping" above. |
| **Release Notes** | system operators, upgrades | Added by #2191, after this audit was first written. Kept as its own tab — see below. |
| **Using the Cloud** | users (cloud tenants) | Today's `User Guide`. A tenant looking for how to drive the OpenStack CLI would never think to look under "Operations", so this audience keeps its own front door rather than being buried in an operator tab. |
| **Contributing** | contributors | Does not exist today. Front door for the 61 external files. |
| **Reference** | all, lookup mode | Component pages, generated workflow docs, hardware schemas, config samples. Does not belong inside a narrative. |

Within Operations the groups are role-aligned, but not everything collapses to
exactly three — several existing groups are already system-operator material and
stay put:

- **Troubleshooting and Architecture** (system operators): the new troubleshooting
  hub, the architecture overview, the five `component-*.md` overview blurbs, and
  the pages that are about diagnosing the deployment as a whole rather than one
  subsystem — `troubleshooting-osh.md`, `logging.md`, `monitoring.md`.
- **OpenStack Services** (system operators): today's per-service `OpenStack`
  group, largely as-is.
- **Platform Services** (system operators): the services UnderStack runs
  *alongside* OpenStack — ArgoCD, Argo Workflows, Gateway API, Nautobot and its
  operator, MariaDB, Postgres, RabbitMQ, Rook Ceph.
- **Hardware** (DC techs): BMC/Redfish, firmware, enrollment — today's
  `Hardware` section, plus `bmc-password.md`.
- **Networking** (network operations): today's `Networking` section.
- **Scripts and Tools** (system operators): cross-cutting, plus
  `ansible-local-usage.md`.

`Infrastructure`'s 17 pages — databases, ingress, Nautobot, logging,
monitoring, Ansible — get sorted across these groups by who actually reads
them, rather than surviving as an uncategorized dumping ground. Most of them
land in **Platform Services**, which is a sixth group but a named and coherent
one: "the supporting services", not "everything else".

Two notes on judgement calls this list originally got wrong:

- `ovs-ovn.md` and `kubectl-us-net.md` are **network operations** tools, so they
  stay in **Networking**. An earlier draft of this document listed them in both
  Networking and the group then called "Architecture & Troubleshooting", which is
  not a thing nav can do.
  The troubleshooting hub links to them instead — which is the point of having a
  hub: a page can be indexed from anywhere while living in exactly one place.
- The supporting services do not fit inside **OpenStack Services**, because
  MariaDB and Nautobot are not OpenStack services. Widening that group's label to
  cover them would have made it meaningless.

`Release Notes` keeps the top-level tab it shipped with, rather than becoming an
"Upgrading" group inside Operations. Its audience is system operators, which is
the Operations audience, so the audience rule does not force the question either
way — this is a nav-placement call, and `docs/release-notes/` keeps its path
regardless. Three reasons to leave it where it is: readers arrive at it from a
version-pin decision rather than from browsing runbooks; it is the only part of
the tree with a freshness contract and CI enforcing it (`release-note-check.yaml`,
`make unreleased-notes`), which is easier to keep visible at the top level; and it
is newly built and linked, so moving it spends redirect and link-fixing budget for
no reader gain. `operator-guide/index.md` already carries an `## Upgrading`
section pointing into it, which is the cross-link that makes a separate tab work.

`User Guide` keeps its own tab as **Using the Cloud** rather than being folded
into Operations. It is only five pages averaging ~110 lines (one of them a
duplicate), and `operator-guide/index.md` already treats `openstack-cli.md` as a
prerequisite — both of which argue for folding it in. But its readers are cloud
consumers, not operators, and the whole point of this redesign is that each
audience gets a front door it will actually look behind. Dropping the
"Introduction" tab is what pays for keeping this one.

Seven tabs is one more than the original six, and it is one more than is
comfortable. If tab count has to come down, spend it in this order: nest
**Using the Cloud** under Operations first — it is the thinnest tab and has the
most operator overlap — then **Release Notes** as an Operations "Upgrading"
group. What must not give is Contributing or the per-role grouping inside
Operations: those are the front doors this whole redesign exists to create.
Note that seven tabs is still a reduction in *top-level* entries from today's
eight.

Also worth dropping `navigation.expand` from `theme.features`: expand-all is
noise at this size.

### The rule for moving files

> Tab labels and nav grouping are free — change them freely. Move a file only
> when its **audience** changes. Never rename a directory for aesthetics.

Consequences:

- **`deploy-guide/` and `operator-guide/` keep their on-disk paths permanently.**
  They map 1:1 to the Deploy and Operations tabs, their URL prefixes are already
  accurate, and they are the paths that in-repo and external links reference.
  Renaming them to `deploy/` and `operations/` would break seven files outside
  `docs/` for zero content benefit — `charts/argocd-understack/values.yaml` (four
  places) and `README.md` for `deploy-guide/`; `scripts/README.md`,
  `go/understackctl/README.md`, `operators/monitoring/README.md`,
  `examples/openstack-notifications/README.md` and
  `ansible/roles/nova_flavors/README.md` for `operator-guide/`.

    It would also **silently disable a check**, which is worse than breaking a
    link. `.pre-commit-config.yaml` scopes the Component Docs Check hook with
    `files: '...|^docs/deploy-guide/components/.*\.md$'`. Rename the directory and
    the hook still passes — it just stops matching anything.
- `user-guide/` also keeps its path, surfaced as the **Using the Cloud** tab.
  Three `examples/*/README.md` files link to `understack/user-guide/`:
  `terraform-trunk-ports`, `tf-multi-node-build` and `tf-multi-node-router`.
- **`release-notes/` keeps its path, and this one is not negotiable.**
  `.github/workflows/release-notes.yaml` writes
  `https://rackerlabs.github.io/understack/release-notes/<series>/#changelog-<tag>`
  into every GitHub release body, and a published release body is not something
  we get to go back and fix. Renaming the directory 404s every past release; even
  retitling a version heading breaks the `#changelog-<tag>` anchor. `Makefile`,
  `.gitignore`, `changelog.d/scriv.ini`, `changelog.d/unreleased.ini`,
  `RELEASING.md` and `.github/workflows/properdocs.yaml` all hardcode the path as
  well.
- **`design-guide/` is the only directory that dies**, because its contents
  genuinely split three ways.

### Phasing

Each phase is a reviewable stream of work. Keep individual PRs small, but land
the phases in this order: correctness and guardrails precede the larger content
moves they are meant to protect.

- **Phase 1 — nav rewrite plus the new front doors. Done.** `nav:` is now the
  seven tabs, using **existing on-disk paths only** — no file moved, so no
  in-repo or external link changed. `Release Notes` carried over untouched,
  including its hand-ordering comment. Added `docs/contributing/index.md`,
  `docs/reference/index.md`, role landing pages for Hardware and Networking, and
  the `docs/operator-guide/troubleshooting.md` hub;
  rewrote the 8-line upstream-forwarding `user-guide/index.md` into a real
  **Using the Cloud** front door and the "Getting Started" card on `docs/index.md`
  into audience cards — six of them, not five, because system operators get one
  for day 0 and one for day 2 rather than being asked which they are. Deleted
  `design-guide/intro.md` and added
  `mkdocs-redirects` carrying its one redirect. Also dropped `navigation.expand`,
  since that only made sense alongside the nav rewrite.

    Three things came up during implementation that the plan above had not
    settled:

    - **`vision.md` is parked on the `Home` tab.** Phase 4 folds it into
      `docs/index.md`, but a page cannot be de-listed in the meantime, so `Home`
      is temporarily a two-page section rather than a single page.
    - **`Platform Services` was needed as a sixth Operations group**, because the
      supporting services have nowhere else to go. See the note above.
    - **`kubernetes.md`, `secrets.md` and `networking.md` sit under `Deploy`**
      with their current filenames. They read oddly there — `networking.md` in
      particular — but renaming them is Phase 4's job, and doing it here would
      have broken the "no file moves" property that makes this phase cheap to
      revert.
- **Phase 2 — correctness.** Fix guidance that can send readers down a known
  wrong path before reorganizing more of the site. At minimum: replace the
  ingress-nginx instructions in `deploy-guide/config-dex.md`, decide whether the
  `ingress-nginx` component page and bootstrap entry should be removed, replace
  the fictional `understack_ref: v1.0.0` examples, resolve published TODOs on the
  primary deployment path, and either add real Ceph/PostgreSQL/BMC diagnostics
  or keep the troubleshooting index scoped to what those pages actually cover.
- **Phase 3 — anti-rot CI.** Land the checks listed below before moving files or
  generating more indexes. Fix the missing `nautobot-worker` component-index row
  and the zero-match workflow dependency glob as part of introducing the checks,
  so each guardrail starts from a clean baseline.
- **Phase 4 — content merges.** Fold `secrets.md` into `secrets-eso-setup.md`
  and the two `server-firmware-update.md` into one. Move `networking.md` to
  `deploy-guide/provisioning-network.md` and `kubernetes.md` to
  `deploy-guide/tools.md`, which dissolves the naming collision. Fold the
  Overview vision statement into `docs/index.md`. Retitle the colliding H1s so
  the three OpenStack Helm pages become "Why We Diverge from OpenStack Helm",
  "openstack-helm (component)" and "Troubleshooting OpenStack Helm".
- **Phase 5 — dissolve `design-guide/`.** Hardware schemas to `reference/`, the
  four design deep-dives to `contributing/design/`, and the architecture
  overview into the Operations **Troubleshooting and Architecture** group,
  consolidated there with the five `component-*.md` overview blurbs. Add the
  missing reciprocal links between the reference and how-to hardware pages.

    This is the phase with real link work, and an earlier draft of this document
    badly undercounted it as "the two `ansible/roles/nova_flavors/` link fixes".
    The actual set is:

    - **17 relative `../design-guide/*.md` links across 6 pages.**
      `operator-guide/openstack-ironic-inspection-guide.md` alone has 9;
      `reference/index.md` has 4 and `contributing/index.md` has 1, both added by
      Phase 1. Redirects do not help here — `validation.not_found` reads the
      markdown source.
    - **One** external link, `ansible/roles/nova_flavors/README.md:15`. Line 243
      of the same file points at `operator-guide/flavors/` and must be left
      alone, which is how the "two fixes" miscount happened.
    - `Makefile` lines 22 and 49, for the generated sample config path.
- **Phase 6 — write the Contributing tab.** The largest writing effort; split
  per-language so each sub-PR has an owner. Add root `CONTRIBUTING.md`, which
  GitHub surfaces in the PR UI alongside the `pull_request_template.md` that now
  exists. Surface `RELEASING.md` in this tab rather than rewriting it — it is
  current, and `RELEASING.md` at the root is the path the CI failure message and
  the PR template point at, so it stays where it is and the tab links to it (or
  includes it via `pymdownx.snippets`, which is already enabled).

Every PR that moves or merges a page must include its redirect map, update all
in-repository links, and pass `make docs`. Before merging a phase, also verify
the old published URLs in the built `site/`, inspect merged pages for duplicate
headings, and confirm the new landing pages still route every advertised task to
content that performs that task.

### Mechanics that are easy to get wrong

- **You cannot de-list a page.** All 137 pages are in `nav:`, and
  `validation.omitted_files` plus `properdocs build --strict` means any file under
  `docs/` missing from `nav:` fails the build. Every reorg step must either place
  a page somewhere in nav or delete it. This is also free orphan detection in
  both directions — do not write a script for it.
- **`release-notes/unreleased.md` is in `nav:` but not in git.** It is generated
  by `make unreleased-notes` and gitignored, so `nav:` and the working tree only
  agree after that target has run. Two consequences: the `docs` and `docs-local`
  targets depend on it and `properdocs build --strict` fails without it, so never
  run `properdocs build` directly during a reorg; and any tool that reconciles
  `nav:` against tracked files needs this file — and the generated
  `docs/workflows/` tree and neutron sample config — on an allowlist.
- **The Release Notes nav list is hand-ordered on purpose.** The comment in
  `properdocs.yml` spells it out: `include_dir_to_nav` only sorts ascending
  ASCII, so `v0.10.md` would land before `v0.9.md`, and its reverse toggle is
  **global** — flipping it for Release Notes would also reverse the generated
  Workflows section. That global-toggle constraint bounds the `docs/workflows/`
  item further down this list: nesting it under Reference is safe because it does
  not change the sort settings, but do not reach for `include_dir_to_nav` to tidy
  any other section.
- **`MD024` is now `siblings_only: true`,** relaxed so release-notes pages can
  repeat "Action required" per version. Duplicate headings are still an error
  between siblings, which is exactly the case Phase 4 creates when it
  concatenates two pages — so the merges still need heading passes.
- **`validation` has no `error` level.** It only accepts `warn`/`info`/`ignore`,
  so `--strict` in the Makefile is the only thing that turns these into failures.
  Do not drop it.
- **Redirects:** a `redirect_maps` key must not be a real file, and its value
  must be a page in the build, or `--strict` fails. So each redirect lands in the
  **same** PR as its move, never before. `mkdocs-redirects` 1.2.3 declares
  compatibility with `properdocs>=1.6.5` and registers under `[mkdocs.plugins]`,
  which properdocs reads, so adding it is safe.
- **Redirects do not satisfy link validation.** `validation.links.not_found`
  checks the markdown source, not the served HTML. Every in-repo markdown link
  has to be really updated; redirects only serve external inbound traffic.
- **Leave `docs/schema/` alone.** It is a directory of symlinks into `schema/`
  and `components/*/values.schema.json`, published at `/schema/*.json` and
  referenced by absolute `$schema=` URLs in `examples/deploy-repo/hardware/**`.
  Not markdown, so `omitted_files` ignores it; guarded by the pre-commit
  `check-symlinks` hook.
- **Leave the generated `docs/workflows/` directory where it is.**
  `include_dir_to_nav` recurses into nested nav lists, so it can be nested under
  Reference with no Makefile change — and a generated tree cannot have explicit
  per-page redirect keys anyway.

### Anti-rot checks worth adding (Phase 3)

Use `.github/workflows/release-note-check.yaml` as the workflow shape: no
`paths:` filter and a short-circuit to success, so the check can be required. A
path-filtered workflow never reports a status on non-matching pull requests and
therefore cannot be required.

1. Make `check-component-docs.py` **bidirectional**, so a deleted template does
   not leave a zombie page. Requires allowlisting the eleven pages that have no
   template of their own (`index` plus the ten OpenStack services).
2. Teach the same script to parse the `application-openstack-helm.yaml` service
   list, so adding a service requires a docs page. This also generates the
   allowlist for check 1.
3. Validate that every component page carries the front-matter keys `macros.py`
   reads. `_render_sources()` returns `""` on a missing key today, so the page
   silently renders an empty bullet list.
4. Generate the component index table from front matter via a new
   `component_table()` macro instead of maintaining 55 rows by hand. This one has
   a live bug to fix, not just a hypothetical: the table is missing
   `nautobot-worker`, and has been since before this audit.
5. `scripts/check-published-links.py` — assert every
   `rackerlabs.github.io/understack/<path>` reference in non-`docs/` files
   resolves inside the built `site/`. This is the check that would have caught
   the `operators/monitoring/README.md` 404, and it is what makes future moves
   safe. It now matters more: `.github/workflows/release-notes.yaml` constructs
   such a URL and writes it into GitHub release bodies, where a 404 is permanent
   because the body is already published. That workflow's URL template belongs in
   this check's scope.
6. A contributor-tab coverage check: every top-level `go/<x>/` and `python/<x>/`
   directory must be mentioned in the Contributing tab. Same shape as
   `check-component-docs.py`, and the thing that stops Phase 6's work decaying
   back into invisible files.

## Status of the work

**Phase 1 is done.** The seven tabs, five new front doors and the troubleshooting
hub are in place; `properdocs build --strict` is clean and
`check-component-docs.py` passes. Nothing moved on disk, so nothing outside
`properdocs.yml` and the pages listed in that phase changed.

**Phases 2 through 6 are unstarted**, and they remain a proposal rather than a
plan of record. Phase 1 was deliberately the phase that commits to nothing: the
findings below still need agreement before pages start moving, and the fastest
way to disagree with the target layout is now to click around the seven tabs and
say what feels wrong.

One piece of the target layout does now exist, arrived at independently: #2191
added the `Release Notes` tab, `docs/release-notes/`, the `changelog.d/` fragment
workflow, `RELEASING.md` and the CI that enforces a note on upgrade-impacting
pull requests. This document has been re-checked against it. Nothing in the
findings was invalidated; the counts moved (133 → 137 pages, 7 → 8 top-level nav
entries, 58 → 61 external markdown files), the proposal grew a seventh tab, and
three new mechanics were added — the generated-but-navigated
`release-notes/unreleased.md`, the global `include_dir_to_nav` sort constraint,
and the immutability of the release-body URLs. Two findings got *worse* evidence
in the process: the fictional `understack_ref: v1.0.0` and the stale
`config-dex.md` are both now contradicted by pages release notes links to.
