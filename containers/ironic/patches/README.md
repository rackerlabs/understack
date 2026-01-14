# Ironic Patches

Patches are derived from cherry-picking patches to the stable series we follow.

[https://github.com/rackerlabs/ironic]

The branch for these are `understack/$OPENSTACK_VERSION`

## To clone everything down do the following:

```bash
git clone https://github.com/openstack/ironic
git checkout --track origin/stable/2025.2
git remote add rackerlabs https://github.com/rackerlabs/ironic
git fetch rackerlabs
git checkout --track rackerlabs/understack/2025.2
```

## So to generate this series of patches for 2025.2 for example:

```bash
git checkout understack/2025.2
git format-patch stable/2025.2 -o PATH/TO/THIS/DIR
```

Now update the `series` file for any new patches.

## Adding patches is done via `git cherry-pick`

```bash
git checkout understack/2025.2
git cherry-pick GITISH_TO_PORT
git push rackerlabs understack/2025.2
```

## Creating the next stable series:

```bash
git checkout --track origin/stable/2026.1
git checkout -b understack/2026.1
```

## Rebasing to keep things clean

```bash
git checkout stable/2025.2
git pull -p
git checkout understack/2025.2
git rebase stable/2025.2
git push rackerlabs understack/2025.2
```
