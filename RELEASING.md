# Releasing UnderStack

Repository-wide `vX.Y.Z` tags are created **manually**. No workflow creates
them. Pushing the tag triggers `containers.yaml` and `containers-openstack.yaml`,
which publish container images tagged with the git ref.

Per-artifact tags (`understackctl/vX.Y.Z`, `nautobotop-vX.Y.Z`,
`kubectl-us-net/vX.Y.Z`, `ironic-hardware-exporter/vX.Y.Z`, `dexop-vX.Y.Z`) are
released independently and are not covered here.

## Where upgrade notes live

Operator-facing upgrade notes live in `docs/release-notes/`, one page per minor
series, listing versions newest-first. Anyone whose change requires operator
action adds a bullet under `Unreleased` on the current series page **in the same
pull request as the change**, and labels the pull request `upgrade-impact`.

Two invariants:

- There is **exactly one `Unreleased` section** across all series pages, always
  on the highest-numbered page.
- **Most releases will not need a note at all.** Tags are cut frequently and
  usually carry nothing an operator has to act on. A version that requires no
  operator action gets **no section**, and cutting it involves no docs change
  whatsoever. Empty sections teach operators that these pages are not worth
  opening, which is the one outcome that makes them useless.

Because `understack_ref` defaults to `HEAD` and the docs site only publishes
`main`, a note merged alongside its change is immediately visible to the
deployments that track `main`. That is the reason notes are written up front
rather than assembled at release time.

## Cutting a patch release

### 1. Review the diff for undocumented operator impact

Not every operator-affecting change gets flagged. Before promoting the notes,
compare the previous tag against `main` over the paths where impact hides:

```bash
git fetch --tags
git diff v0.4.25..main --stat -- \
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

Anything you find here that is not already under `Unreleased` is a gap. Add it
now.

### 2. Promote the `Unreleased` section

**If every subsection under `Unreleased` still says `_Nothing yet._`, there is
nothing to do here.** Leave the page alone and skip to step 3 to tag. This is
the common case.

Otherwise, in the current series page, for example `docs/release-notes/v0.4.md`:

1. Change `## Unreleased` to `## v0.4.26` and add the metadata lines
   (`**Released:**`, `**Impact:**`, `**Applies to:**`).
2. Delete any subsection whose only content is `_Nothing yet._`.
3. Insert a fresh `## Unreleased` block above it, copied from the template
   below.

Then open a pull request titled `docs: release notes for v0.4.26` and merge it
before tagging, so the tag contains its own notes.

### 3. Tag the release

Tag the current tip of `main`:

```bash
git checkout main && git pull
git tag -a v0.4.26 -m "v0.4.26"
git push origin v0.4.26
```

### 4. Create the GitHub release

Create the release from the tag with auto-generated notes. If this version got a
section in step 2, add one line at the top of the body pointing at it:

```markdown
**Upgrading?** See the
[v0.4.26 upgrade notes](https://rackerlabs.github.io/understack/release-notes/v0.4/#v0426).
```

If it got no section, leave the body as generated. Do not link a section that
does not exist.

### 5. Confirm the builds

Check that `containers.yaml` and `containers-openstack.yaml` succeeded for the
tag.

## Cutting a minor release

A new series always gets a page, whether or not the release itself has notes,
because that page is where subsequent `Unreleased` notes go. Same as above, but
first:

1. Create `docs/release-notes/v0.5.md` with a `# Release Notes: v0.5.x`
   heading.
2. Move the `Unreleased` block out of `v0.4.md` into `v0.5.md`. If it has
   content, promote that content to `## v0.5.0` and leave a fresh `Unreleased`
   block above it. If it is empty, just leave the empty `Unreleased` block on
   the new page. Either way `v0.4.md` ends up with no `Unreleased` section.
3. Add `- release-notes/v0.5.md` to `properdocs.yml` **above** the v0.4 entry.
   Forgetting this fails the docs build, which is intentional.
4. Update the series table in `docs/release-notes/index.md`: mark v0.5.x
   Current and v0.4.x Maintenance.
5. Update the `Unreleased` anchor in the "If you deploy from `main`" callout in
   `docs/release-notes/index.md` to point at the new page.

## Section template

Copy this for a new version section. Include only the subsections that apply
and delete the rest: an empty `Rollback` heading is worse than no `Rollback`
heading.

Two authoring constraints in this repo. The `nl2br` extension is enabled, so a
single newline inside a paragraph renders as a line break. And markdownlint sets
`MD007: indent: 4`, so nested list items are indented by four spaces.

````markdown
## v0.4.26

**Released:** 2026-08-11
**Impact:** Action required
**Applies to:** site clusters

### Summary

One or two sentences on what changed and why an operator has to care. Link the
pull request or issue for the underlying detail.

### Action required

Ordered and copy-pasteable, in the order the steps must be performed.

1. Do the first thing.

    ```bash
    kubectl -n openstack get pods
    ```

2. Do the second thing.

### Deploy repo changes

Show before and after, using the real path.

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  neutron:
    enabled: true
```

### Secrets

- **New:** `<secret-name>` in namespace `<ns>`, keys `<k1>`, `<k2>`.
- **Removed:** `<secret-name>`, safe to delete after upgrading.

### Chart and image versions

- OpenStack-Helm `neutron` chart: `<old>` to `<new>`
  (`charts/argocd-understack/values.yaml`).
- `keystone` image series: `<old>` to `<new>`
  (`components/images-openstack.yaml`). Series tags are moving tags rebuilt
  from `main`, and `pull_policy` is `Always`, so a resync pulls the current
  build.

### Verification

How an operator confirms the upgrade worked.

```bash
kubectl -n openstack get pods
```

### Rollback

State honestly whether rollback is possible. If it is, set `understack_ref`
back to `v0.4.25` and resync. If it is not, say so plainly and give the
recovery path instead.

### Known issues

- None.
````
