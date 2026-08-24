# Nova Patches

Patches are derived from cherry-picking patches to the stable series we follow.

[https://github.com/rackerlabs/nova](https://github.com/rackerlabs/nova)

The branch for these are `understack/$OPENSTACK_VERSION`

## Initial Setup - Creating understack/2026.1 Branch

If the `understack/2026.1` branch doesn't exist yet, create it:

```bash
git clone https://github.com/openstack/nova
cd nova
git checkout --track origin/stable/2026.1
git remote add rackerlabs https://github.com/rackerlabs/nova
git checkout -b understack/2026.1
git push -u rackerlabs understack/2026.1
```

## To clone everything down (after branch is created)

```bash
git clone https://github.com/openstack/nova
git checkout --track origin/stable/2026.1
git remote add rackerlabs https://github.com/rackerlabs/nova
git fetch rackerlabs
git checkout --track rackerlabs/understack/2026.1
```

## Adding patches is done via `git cherry-pick`

```bash
git checkout understack/2026.1
git cherry-pick GITISH_TO_PORT
git push rackerlabs understack/2026.1
```

## Creating the next stable series

```bash
git checkout --track origin/stable/2026.2
git checkout -b understack/2026.2
```

## Rebasing to keep things clean

The `scripts/git-understack-rebase` script in the understack repo automates this: it checks your
remotes and branches, shows you the commits involved, performs the rebase, and force-pushes both
branches to `rackerlabs` after you confirm each step. It expects a remote named `upstream`
(pointing at `openstack/nova`, not `origin`) and a remote named `rackerlabs`.

```bash
scripts/git-understack-rebase ~/work/nova 2026.1
```

### Patches that landed upstream (possibly tweaked)

Before rebasing, the script checks whether any patch we carry has since landed
in `upstream/stable/$VERSION`. It matches on the Gerrit `Change-Id:` trailer,
which survives cherry-picking, so it recognizes our copy of a change even if the
content drifted. It then splits the matches into two groups:

- **identical** — same content as upstream. `git rebase` drops these on its own;
  the script just tells you it happened.
- **MODIFIED** — same `Change-Id` but the content differs. This is the case that
  bit us in [understack#2232](https://github.com/rackerlabs/understack/pull/2232):
  a patch was cherry-picked, then tweaked (a reworded release note) before it
  merged upstream, so git could not drop it by patch-id and it conflicted.

For the MODIFIED group the script prompts you. The default is to **drop them and
keep upstream's version** (done by scripting an interactive rebase to mark those
commits `drop`). If you decline, they are replayed as-is and you resolve the
conflicts by hand, preferring upstream. Either way you are told exactly which
commits are involved before anything is rewritten.

To do it manually instead:

```bash
git checkout stable/2026.1
git pull -p
git checkout understack/2026.1
git rebase stable/2026.1
git push rackerlabs understack/2026.1
```

## Updating the container

```bash
git checkout understack/2026.1
git show
# ensure the git-ish in the Dockerfile matches
```

## Backporting patches from upstream master

To backport a patch from upstream master (or another branch) to understack/2026.1:

```bash
# Fetch all branches from upstream (openstack/nova)
# This fetches master, stable branches, and all other refs
git fetch origin

# Fetch all branches from rackerlabs fork
git fetch rackerlabs

# Checkout the understack branch
git checkout understack/2026.1

# Cherry-pick the commit from master
# You can get the commit hash from the PR or upstream repository
git cherry-pick <UPSTREAM_COMMIT_HASH>

# If there are conflicts, resolve them:
git add <conflicted-files>
git cherry-pick --continue

# Push to rackerlabs fork
git push rackerlabs understack/2026.1
```

### Example workflow for a specific PR

Following the backporting workflow above results in a PR like https://github.com/rackerlabs/nova/pull/XXX:

1. Find the commit hash from upstream master
2. Cherry-pick it to the branch: `git cherry-pick <COMMIT_HASH>`
3. Resolve any conflicts if needed
4. Test the changes locally
5. Push to the rackerlabs understack branch

### Note on patch sources

Patches can come from:
- OpenStack upstream master branch (`openstack/nova` - origin/master)
- Other branches or forks that have fixes needed
