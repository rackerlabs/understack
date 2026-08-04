# Documentation Layout Audit

**Status:** proposal, for team review. This file is a planning artifact, not
product documentation. Delete it once the phases below have landed or been
rejected.

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

133 markdown pages, all of them listed in the hand-maintained `nav:`. Seven
top-level entries: `Home`, `Overview`, `Design Guide`, `Deployment Guide`,
`Operator Guide`, `User Guide`, `Workflows`.

Two pages are generated at build time (`docs/workflows/` from
`scripts/argo-workflows-to-mkdocs.py`, and the neutron sample config from
`oslo-config-generator`), and 55 of the 133 are component reference pages under
`docs/deploy-guide/components/`.

Separately, **58 markdown files live outside `docs/`** and are invisible to the
site. Several are substantial: `go/ironic-hardware-exporter/README.md` (436
lines), `python/understack-tests/README.md` (379),
`charts/argocd-understack/README.md` (268), `go/dexop/README.md` (231),
`ansible/README.md` (162). There is also a third docs tree at
`workflows/argo-events/docs/`.

## Findings

### The big one: no contributor documentation exists

There is no contributor section on the site and no `CONTRIBUTING.md` in the
repository. Everything a new developer needs is in those 58 external files, which
are unlinked, unlinted for links, and drifting. The clearest symptom is three
near-identical `DEVELOPMENT.md` files (`python/ironic-understack/`,
`python/neutron-understack/`, `python/understack-workflows/`) that differ by a
handful of lines — the classic copy-paste decay.

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
  early.
- `deploy-guide/components/ingress-nginx.md` still exists as an enabled-component
  page; `bootstrap/README.md` also still lists `ingress-nginx` as a bootstrap
  component, and lists only three of the four directories that are actually
  there.
- `README.md` tells you to run `nix-shell`. There is no `shell.nix` or
  `flake.nix` in the repository.
- `operator-guide/argocd-helm-chart.md` shows `understack_ref: v1.0.0  # Pin to
  specific version`. There is no `v1.x` series; the newest tag is `v0.4.25`.
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

### The 55 component pages

Roughly 27 are 45–51 line near-identical template output; `nautobot-worker.md` is
762 lines, about 30x the median. They are machine-shaped reference material
sitting inside the install narrative. The hand-maintained 55-row table in
`deploy-guide/components/index.md` is already visibly rotting: the ten OpenStack
services are appended out of alphabetical order.

### Build and CI hygiene

- `docs/overrides/assets/stylesheets/custom.f7ec4df2.min.css` and its `.map` are
  committed, content-hashed **build output**, referenced by nothing —
  `extra_css` points only at `stylesheets/rackspace-theme.css`, and no
  `theme.custom_dir` is configured. They are the only files in
  `docs/overrides/`.
- `requirements-docs.txt` installs three plugins that are not enabled in
  `plugins:` and are unused: `mkdocs-swagger-ui-tag`, `mkdocs-glightbox`,
  `mkdocs-multirepo-plugin`.
- `docs/assets/mermaid.min.js` is 2.75 MB vendored into the repository.
- `Makefile:22`'s `WFTMPLS := $(wildcard components/*-workflows/*/workflowtemplates/*.yaml)`
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

Six tabs. `Home` is a router and `Reference` is cross-cutting lookup; the other
four map onto the five audiences, with system operators spanning both `Deploy`
(day 0) and `Operations` (day 2). There is deliberately no "Introduction" tab:
with no evaluator audience left to sit and read one end-to-end, the short "what
this is / how it is shaped" overview belongs on `Home`, and the architecture
depth a system operator actually needs belongs in `Operations`, next to the
troubleshooting it supports.

| Tab | Audience | Why |
| --- | --- | --- |
| **Home** | router | Already has `hide: [navigation, toc]` and a card grid. Becomes an explicit router across the five audiences, and carries the short project overview. |
| **Deploy** | system operators, day 0 | A linear install narrative with a beginning and an end. |
| **Operations** | system operators, DC techs, network operations, day 2 | The runbook library you land in from a pager, reorganized into role-aligned nav groups instead of one flat list — this is the fix for "Operator Guide grouping" above. |
| **Using the Cloud** | users (cloud tenants) | Today's `User Guide`. A tenant looking for how to drive the OpenStack CLI would never think to look under "Operations", so this audience keeps its own front door rather than being buried in an operator tab. |
| **Contributing** | contributors | Does not exist today. Front door for the 58 external files. |
| **Reference** | all, lookup mode | Component pages, generated workflow docs, hardware schemas, config samples. Does not belong inside a narrative. |

Within Operations the groups are role-aligned, but not everything collapses to
exactly three — two existing groups are already system-operator material and
stay put:

- **Architecture & Troubleshooting** (system operators): the architecture
  overview and the five `component-*.md` overview blurbs, plus the new
  troubleshooting hub and `troubleshooting-osh.md`, `ovs-ovn.md`,
  `kubectl-us-net.md`, `logging.md`.
- **OpenStack Services** (system operators): today's per-service `OpenStack`
  group, largely as-is.
- **Hardware** (DC techs): BMC/Redfish, firmware, enrollment — today's
  `Hardware` section, largely as-is.
- **Networking** (network operations): today's `Networking` section.
- **Scripts and Tools** (system operators): cross-cutting, kept as-is.

`Infrastructure`'s 17 pages — databases, ingress, Nautobot, logging,
monitoring, Ansible — get sorted across these groups by who actually reads
them, rather than surviving as a sixth, uncategorized dumping ground.

`User Guide` keeps its own tab as **Using the Cloud** rather than being folded
into Operations. It is only five pages averaging ~110 lines (one of them a
duplicate), and `operator-guide/index.md` already treats `openstack-cli.md` as a
prerequisite — both of which argue for folding it in. But its readers are cloud
consumers, not operators, and the whole point of this redesign is that each
audience gets a front door it will actually look behind. Dropping the
"Introduction" tab is what pays for keeping this one.

If six tabs still feels like one too many, the pressure valve is to nest
**Using the Cloud** back under Operations — it is the thinnest tab and has the
most operator overlap. What must not give is Contributing or the per-role
grouping inside Operations: those are the front doors this whole redesign
exists to create.

Also worth dropping `navigation.expand` from `theme.features`: expand-all is
noise at this size.

### The rule for moving files

> Tab labels and nav grouping are free — change them freely. Move a file only
> when its **audience** changes. Never rename a directory for aesthetics.

Consequences:

- **`deploy-guide/` and `operator-guide/` keep their on-disk paths permanently.**
  They map 1:1 to the Deploy and Operations tabs, their URL prefixes are already
  accurate, and they are the paths that in-repo and external links reference.
  Renaming them to `deploy/` and `operations/` would break
  `charts/argocd-understack/values.yaml` (four places), `README.md`,
  `scripts/README.md`, `go/understackctl/README.md`,
  `examples/openstack-notifications/README.md` and three
  `examples/*/README.md` — for zero content benefit.
- `user-guide/` also keeps its path, surfaced as the **Using the Cloud** tab.
- **`design-guide/` is the only directory that dies**, because its contents
  genuinely split three ways.

### Phasing

Each phase is a separate reviewable PR.

- **Phase 1 — nav rewrite plus the new front doors.** This is the phase that
  delivers the front doors. Rewrite `nav:` to the six tabs using **existing
  on-disk paths only** — no file moves. Add `docs/contributing/index.md`,
  `docs/reference/index.md` and a `docs/operator-guide/troubleshooting.md` hub,
  and rewrite the 8-line upstream-forwarding `user-guide/index.md` into a real
  **Using the Cloud** front door. Rewrite the "Getting Started" card on
  `docs/index.md` into five audience cards — system operators, DC techs, network
  operations, users, contributors (cheapest high-value edit in the whole plan).
  Delete `design-guide/intro.md`. Add `mkdocs-redirects`. Revertable by
  reverting one file, with zero external breakage.
- **Phase 2 — content merges.** Fold `secrets.md` into `secrets-eso-setup.md`
  and the two `server-firmware-update.md` into one. Move `networking.md` to
  `deploy-guide/provisioning-network.md` and `kubernetes.md` to
  `deploy-guide/tools.md`, which dissolves the naming collision. Fold the
  Overview vision statement into `docs/index.md`. Retitle the colliding H1s so
  the three OpenStack Helm pages become "Why We Diverge from OpenStack Helm",
  "openstack-helm (component)" and "Troubleshooting OpenStack Helm".
- **Phase 3 — dissolve `design-guide/`.** Hardware schemas to `reference/`, the
  four design deep-dives to `contributing/design/`, and the architecture
  overview into the Operations **Architecture & Troubleshooting** group,
  consolidated there with the five `component-*.md` overview blurbs. Needs the
  `Makefile` edit for the generated sample config path and the two
  `ansible/roles/nova_flavors/` link fixes. Add the missing reciprocal links
  between the reference and how-to hardware pages.
- **Phase 4 — write the Contributing tab.** The largest writing effort; split
  per-language so each sub-PR has an owner. Add root `CONTRIBUTING.md`, which
  GitHub surfaces in the PR UI.
- **Phase 5 — anti-rot CI.**

### Mechanics that are easy to get wrong

- **You cannot de-list a page.** All 133 pages are in `nav:`, and
  `validation.omitted_files` plus `properdocs build --strict` means any file under
  `docs/` missing from `nav:` fails the build. Every reorg step must either place
  a page somewhere in nav or delete it. This is also free orphan detection in
  both directions — do not write a script for it.
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

### Anti-rot checks worth adding (Phase 5)

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
   `component_table()` macro instead of maintaining 55 rows by hand.
5. `scripts/check-published-links.py` — assert every
   `rackerlabs.github.io/understack/<path>` reference in non-`docs/` files
   resolves inside the built `site/`. This is the check that would have caught
   the `operators/monitoring/README.md` 404, and it is what makes future moves
   safe.
6. A contributor-tab coverage check: every top-level `go/<x>/` and `python/<x>/`
   directory must be mentioned in the Contributing tab. Same shape as
   `check-component-docs.py`, and the thing that stops Phase 4's work decaying
   back into invisible files.

## Status of the work

**Everything above is unstarted**, including Phase 1. Phases 1 through 5
are a proposal, not a plan of record — the point of this document is to get
agreement on the target layout before anyone starts moving pages.
