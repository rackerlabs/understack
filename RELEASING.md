# Releasing UnderStack

Repository-wide `vX.Y.Z` tags are created **manually**. No workflow creates
them. Pushing the tag triggers `containers.yaml` and `containers-openstack.yaml`
to publish container images, and `release-notes.yaml` to assemble the release
notes and create the GitHub release.

Per-artifact tags (`understackctl/vX.Y.Z`, `nautobotop-vX.Y.Z`,
`kubectl-us-net/vX.Y.Z`, `ironic-hardware-exporter/vX.Y.Z`, `dexop-vX.Y.Z`,
`ironic-ipxe/vX.Y.Z`) are released independently. See
[Separately released artifacts](#separately-released-artifacts) below.

## Writing a release note

Operator-facing upgrade notes live in `docs/release-notes/`, one page per minor
series. You never edit those pages directly. Instead, anyone whose change
requires operator action adds a **fragment** in the same pull request as the
change:

```bash
scriv create
```

That writes `changelog.d/<date>_<you>_<branch>.md`. Uncomment the section that
fits, write the note, and commit it. Also label the pull request
`upgrade-impact`, which is what makes CI require the fragment.

Three things to keep in mind:

- **Most changes need no fragment.** Tags are cut frequently and usually carry
  nothing an operator has to act on. A release with no fragments gets no
  section on the series page and needs no docs change at all. Empty sections
  teach operators that these pages are not worth opening.
- **Write for an operator who has to act**, not for a reviewer reading the
  diff. Fragments are copied verbatim into the page, so use as much room as the
  instructions need: numbered steps, fenced code blocks, before-and-after YAML.
- **You do not write a version number anywhere.** The version is applied when
  the release is tagged.

Because the docs site publishes `main` and `understack_ref` defaults to `HEAD`,
a merged fragment appears on the generated
[Unreleased](docs/release-notes/index.md) page as soon as its change lands, so
deployments tracking `main` see it immediately.

To preview what the notes will look like:

```bash
make unreleased-notes && cat docs/release-notes/unreleased.md
```

## Cutting a patch release

### 1. Review the diff for undocumented operator impact

Not every operator-affecting change gets flagged. Before tagging, compare the
previous tag against `main` over the paths where impact hides:

```bash
git fetch --tags
git diff v0.4.26..main --stat -- \
  charts/argocd-understack/values.yaml \
  charts/argocd-understack/templates/ \
  components/images-openstack.yaml
```

Look specifically for:

- new, renamed or removed `enabled:` keys under `global:` or `site:`
- OpenStack-Helm `chartVersion` bumps, especially ones crossing a release
  series (for example `2025.2` to `2026.1`)
- OpenStack image series changes in `components/images-openstack.yaml`
- added or removed `application-*.yaml` templates, or new services added to the
  service list in `application-openstack-helm.yaml`

Anything you find that has no fragment is a gap. Add one and merge it before
tagging.

### 2. Tag the release

```bash
git checkout main && git pull
git tag -a v0.4.27 -m "v0.4.27"
git push origin v0.4.27
```

That is the whole release procedure. `release-notes.yaml` then:

1. Collects the fragments **as of the tagged commit** into
   `docs/release-notes/v0.4.md` and opens a
   `[Bot] docs: release notes for v0.4.27` pull request against `main`.
2. Creates the GitHub release with auto-generated notes, adding a link to the
   upgrade notes only if there were fragments to collect.

### 3. Merge the notes pull request

If the workflow opened one, review the wording and merge it. Until it merges,
the "Upgrading?" link in the release body 404s, so do not leave it sitting.

The notes land on `main` one commit *after* the tag, so the tag does not contain
its own rendered notes. This is intentional — collecting against the tag rather
than against `main` is what stops a fragment merged moments after tagging from
being filed under a release that does not contain it. Nothing builds the docs
from a tag checkout, and the site publishes from `main`, so the published notes
are correct either way.

### 4. Confirm the builds

Check that `containers.yaml` and `containers-openstack.yaml` succeeded for the
tag.

## Cutting a minor release

Same as above, but first open the new series page:

1. Create `docs/release-notes/v0.5.md`, copying the preamble and the
   `<!-- scriv-insert-here -->` marker from `v0.4.md`. Do not copy any version
   sections.
2. Point scriv at it by changing `changelog` in `changelog.d/scriv.ini` to
   `docs/release-notes/v0.5.md`. This is the only configuration a minor release
   needs, and forgetting it files v0.5 notes on the v0.4 page.
3. Add `- release-notes/v0.5.md` to `properdocs.yml` **above** the v0.4 entry.
   Forgetting this fails the docs build, which is intentional.
4. Update the series table in `docs/release-notes/index.md`: mark v0.5.x
   Current and v0.4.x Maintenance.

Fragments are series-agnostic, so anything already in `changelog.d/` collects
onto whichever page is configured. There is no block to move.

## Separately released artifacts

The CLI utilities, operators and images that carry their own tag namespace do
**not** get release notes. Their GitHub release bodies are asset-only, or
written by hand.

This is deliberate rather than an oversight. GitHub's note generator has no path
awareness in a monorepo: the range `understackctl/v0.0.4..understackctl/v0.0.5`
spans 205 merge commits, almost none of them touching `understackctl`. Turning
on `generate_release_notes` for those workflows would produce 200 lines of
unrelated platform churn, which is worse than an empty body.

If a body is worth writing, write it by hand, or scope it by path:

```bash
git log understackctl/v0.0.4..understackctl/v0.0.5 \
  --merges --pretty='- %s' -- go/understackctl/
```

Changes confined entirely to one of these subtrees are labelled
`skip-changelog` by `labeler.yaml` and excluded from the platform release notes
by `.github/release.yml`, so they are announced once rather than twice. The
label can also be applied by hand to keep any pull request out of the notes.

## How the pieces fit together

| File | Role |
| ---- | ---- |
| `changelog.d/` | Release note fragments awaiting a release |
| `changelog.d/scriv.ini` | Which series page fragments collect into |
| `changelog.d/unreleased.ini` | Config for the generated Unreleased page |
| `.github/workflows/release-note-check.yaml` | Requires a fragment on upgrade-impacting pull requests |
| `.github/workflows/release-notes.yaml` | Collects on tag, opens the pull request, creates the release |
| `.github/release.yml` | Categories and exclusions for auto-generated notes |
| `.github/labeler.yml` | Path-derived labels that drive those exclusions |

Every scriv command must run from the repository root: `changelog` in
`scriv.ini` is resolved relative to the working directory, and scriv only reads
that config because it sits inside `changelog.d/`.
