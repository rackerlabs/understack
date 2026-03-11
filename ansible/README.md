# Running Ansible locally

The Ansible container is built by [`.github/workflows/containers.yaml`](../.github/workflows/containers.yaml) from [`containers/ansible/Dockerfile`](../containers/ansible/Dockerfile). That image copies this directory into `/runner/project` and the Argo workflow in [`workflows/argo-events/workflowtemplates/ansible-run.yaml`](../workflows/argo-events/workflowtemplates/ansible-run.yaml) expects inventory at `/runner/inventory/hosts.yaml`.

## Build the container

From the repository root:

```bash
docker build -f containers/ansible/Dockerfile -t understack-ansible .
```

## Run locally with a Python virtualenv

This uses the same Python packages and Ansible collections installed by the container build.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r ansible/requirements.txt
ansible-galaxy collection install -r ansible/requirements.yml
```

Prepare inventory:

```bash
mkdir -p .local/ansible/inventory
cp /path/to/your/inventory.yaml .local/ansible/inventory/hosts.yaml
```

If the playbook talks to OpenStack, put `clouds.yaml` in a standard OpenStack location:

```bash
mkdir -p ~/.config/openstack
cp /path/to/clouds.yaml ~/.config/openstack/clouds.yaml
```

Run playbooks from the `ansible/` directory so the local roles resolve from `./roles`:

```bash
cd ansible
ansible-playbook -i ../.local/ansible/inventory/hosts.yaml debug.yaml -vvv
```

Examples:

```bash
cd ansible
ansible-playbook -i ../.local/ansible/inventory/hosts.yaml image-upload.yaml -vvv
ansible-playbook -i ../.local/ansible/inventory/hosts.yaml keystone-post-deploy.yaml -vvv
```

Notes:

- activate the virtualenv with `source .venv/bin/activate` before running playbooks in a new shell
- `image-upload.yaml` needs a `glance` group in inventory and valid OpenStack credentials
- `nova-post-deploy.yaml` also needs flavor and device-type data; override the role paths or create local symlinks to match the defaults under `/runner/data`
- Nautobot playbooks may also need `NAUTOBOT_TOKEN` exported in your shell

## Prepare local input files

Create a local inventory file at the same path the workflow uses in-cluster:

```bash
mkdir -p .local/ansible/inventory
cp /path/to/your/inventory.yaml .local/ansible/inventory/hosts.yaml
```

If the playbook talks to OpenStack, mount a `clouds.yaml` file into a standard OpenStack location inside the container:

```bash
mkdir -p .local/openstack
cp ~/.config/openstack/clouds.yaml .local/openstack/clouds.yaml
```

If the playbook needs extra mounted data, keep the same paths it expects in-cluster:

- `nova-post-deploy.yaml`: mount flavors at `/runner/data/flavors/` and device types at `/runner/data/device-types/`
- playbooks using Nautobot: set `NAUTOBOT_TOKEN`
- commands matching the Argo workflow: set `UNDERSTACK_ENV`

## Run a playbook with ansible-runner

This matches the Argo workflow shape closely. The repo copy is mounted over `/runner/project` so local edits are used without rebuilding the image.

```bash
docker run --rm -it \
  -v "$PWD/ansible:/runner/project" \
  -v "$PWD/.local/ansible/inventory:/runner/inventory" \
  -v "$PWD/.local/openstack:/etc/openstack:ro" \
  -e UNDERSTACK_ENV=dev \
  -e NAUTOBOT_TOKEN="$NAUTOBOT_TOKEN" \
  understack-ansible \
  ansible-runner run /tmp/runner \
  --project-dir /runner/project \
  --playbook debug.yaml \
  --cmdline "-i /runner/inventory/hosts.yaml --extra-vars 'env=dev' -vvv"
```

Notes:

- `ansible-runner` must be passed explicitly because the image entrypoint is `dumb-init`
- replace `debug.yaml` with the playbook you want to run
- if a playbook does not use Nautobot, omit `NAUTOBOT_TOKEN`
- if a playbook does not use OpenStack, omit the `/etc/openstack` mount

## Example: run the image upload playbook

[`image-upload.yaml`](./image-upload.yaml) targets the `glance` group and uses OpenStack auth, so the inventory needs a `glance` host or group and the container needs `clouds.yaml`:

```bash
docker run --rm -it \
  -v "$PWD/ansible:/runner/project" \
  -v "$PWD/.local/ansible/inventory:/runner/inventory" \
  -v "$PWD/.local/openstack:/etc/openstack:ro" \
  understack-ansible \
  ansible-runner run /tmp/runner \
  --project-dir /runner/project \
  --playbook image-upload.yaml \
  --cmdline "-i /runner/inventory/hosts.yaml -vvv"
```

## Example: run the Nova flavor playbook

[`nova-post-deploy.yaml`](./nova-post-deploy.yaml) also expects ConfigMap-style data directories. Mount local directories to the same paths:

```bash
docker run --rm -it \
  -v "$PWD/ansible:/runner/project" \
  -v "$PWD/.local/ansible/inventory:/runner/inventory" \
  -v "$PWD/.local/openstack:/etc/openstack:ro" \
  -v "$PWD/hardware/flavors:/runner/data/flavors:ro" \
  -v "$PWD/hardware/device-types:/runner/data/device-types:ro" \
  understack-ansible \
  ansible-runner run /tmp/runner \
  --project-dir /runner/project \
  --playbook nova-post-deploy.yaml \
  --cmdline "-i /runner/inventory/hosts.yaml -vvv"
```

## Run with ansible-playbook instead

If you want a simpler interactive container shell:

```bash
docker run --rm -it \
  -v "$PWD/ansible:/runner/project" \
  -v "$PWD/.local/ansible/inventory:/runner/inventory" \
  -v "$PWD/.local/openstack:/etc/openstack:ro" \
  --workdir /runner/project \
  --entrypoint /bin/bash \
  understack-ansible
```

Then run:

```bash
ansible-playbook -i /runner/inventory/hosts.yaml debug.yaml -vvv
```
