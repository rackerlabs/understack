# Ironic Patches

Patches are derived from cherry-picking patches to the stable series we follow.

[https://github.com/rackerlabs/ironic]

The branch for these are `understack/$OPENSTACK_VERSION`

## To clone everything down do the following

```bash
git clone https://github.com/openstack/ironic
git checkout --track origin/stable/2025.2
git remote add rackerlabs https://github.com/rackerlabs/ironic
git fetch rackerlabs
git checkout --track rackerlabs/understack/2025.2
```

## Adding patches is done via `git cherry-pick`

```bash
git checkout understack/2025.2
git cherry-pick GITISH_TO_PORT
git push rackerlabs understack/2025.2
```

## Creating the next stable series

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

## Updating the container

```bash
git checkout understack/2025.2
git show
# ensure the git-ish in the Dockerfile matches
```

## iPXE

We have experienced problems with OSH stock iPXE firmware image and its
compatibility with Nexus switches.

The changed version disables IPv6, LACP and EAPOL.
Customised EFI image is built as part of the Ironic container build.

For debugging purposes, it can also be built manually.

### Manually Compiling iPXE firmware for UnderStack

## Steps

- Run the debian 12 container:

```bash
docker run -it --name ipxe_compiler -v $(pwd):/src -w /src debian:13 bash
```

- Install build dependencies inside that container

```bash
apt update && apt install -y git build-essential bison flex libssl-dev
```

- Compile (DEBUG version)

```bash
cd /src
make bin-x86_64-efi/snponly.efi DEBUG=tcp:3,xfer:3,netdevice:2,ipv4:2,httpcore:2,httpconn:2
```

- Compile (standard version)

```bash
cd /src
make bin-x86_64-efi/snponly.efi
```

- Upload

```bash
kubectl cp bin-x86_64-efi/snponly.efi -c ironic-conductor-http ironic-conductor-0:/var/lib/openstack-helm/httpboot/snponly.efi
```

> [!NOTE]
> This upload is just an example for quick hacking in dev environment. Use
> appropriate method for staging and production releases.
