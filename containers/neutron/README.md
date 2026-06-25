# Neutron Patches

Patches are derived from cherry-picking patches to the stable series we follow.

[https://github.com/rackerlabs/neutron]

The branch for these are `understack/$OPENSTACK_VERSION`

## To clone everything down do the following

```bash
git clone https://github.com/openstack/neutron
git checkout --track origin/stable/2026.1
git remote add rackerlabs https://github.com/rackerlabs/neutron
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
# Fetch all branches from upstream (openstack/neutron)
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

Following the backporting workflow above results in a PR like https://github.com/rackerlabs/neutron/pull/XXX:

1. Find the commit hash from upstream master
2. Cherry-pick it to the branch: `git cherry-pick <COMMIT_HASH>`
3. Resolve any conflicts if needed
4. Test the changes locally
5. Push to the rackerlabs understack branch

### Note on patch sources

Patches can come from:
- OpenStack upstream master branch (`openstack/neutron` - origin/master)
- Other branches or forks that have fixes needed
