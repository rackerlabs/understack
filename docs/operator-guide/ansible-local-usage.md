# Running Ansible Playbooks Locally with Docker

This guide explains how to run Understack Ansible playbooks locally
using the containerized Ansible environment.

## TL;DR

Quick start with local playbook development:

```bash
docker run --rm -it \
  -v $(pwd)/ansible:/runner/project \
  -v $(pwd)/ansible/roles:/runner/project/roles \
  -v $(pwd)/ansible/vars:/runner/project/vars \
  -v /path/to/environment-specific/inventory:/runner/inventory \
  -e NAUTOBOT_URL=https://nautobot.example.com \
  -e NAUTOBOT_TOKEN=your_token_here \
  -e env=dev
  -e EXTRA_VARS='{"password":"secret","token":"abc123","username":"user"}'
  -w /runner \
  ghcr.io/rackerlabs/understack/ansible:latest \
  ansible-runner run /runner --playbook your-playbook.yaml
```

**Note:** Replace `/path/to/environment-name/inventory` with your actual environment inventory path, for example:

- Dev: `/path/to/undercloud-deploy/{environment-name}/inventory`

For OpenStack playbooks, add these environment variables:

```bash
  -e OS_USERNAME=admin \
  -e OS_PASSWORD=your_password \
  -e OS_PROJECT_NAME=admin \
  -e OS_AUTH_URL=https://keystone.example.com/v3 \
  -e OS_USER_DOMAIN_NAME=Default \
  -e OS_PROJECT_DOMAIN_NAME=Default \
  -e OS_DEFAULT_DOMAIN=default \
```

## Container Overview

The Ansible container (`ghcr.io/rackerlabs/understack/ansible`) is built from `containers/ansible/Dockerfile`

The container uses `ansible-runner` as its default command and expects playbooks to be located in `/runner/project/`.

## Interactive Shell for Debugging

Drop into a bash shell to explore or debug:

```bash
docker run --rm -it \
  -v $(pwd)/ansible:/runner/project \
  -v $(pwd)/ansible/roles:/runner/project/roles \
  -v $(pwd)/ansible/vars:/runner/project/vars \
  -v /path/to/undercloud-deploy/bravo-uc-iad3-dev/inventory:/runner/inventory \
  -e NAUTOBOT_URL=https://nautobot.example.com \
  -e NAUTOBOT_TOKEN=your_token \
  -w /runner \
  ghcr.io/rackerlabs/understack/ansible:latest \
  bash
```

Once inside, you can run playbooks manually:

```bash
ansible-runner run /runner --playbook your-playbook.yaml
```

## Volume Mounts Explained

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `$(pwd)/ansible` | `/runner/project` | Main playbook directory |
| `$(pwd)/ansible/roles` | `/runner/project/roles` | Ansible roles |
| `$(pwd)/ansible/vars` | `/runner/project/vars` | Variable files |
| `/path/to/environment/inventory` | `/runner/inventory` | Environment-specific inventory files |

**Important:** The inventory directory is environment-specific and should be mounted from your deployment directory structure.
The inventory is assembled from multiple files:

- Environment inventory: `undercloud-deploy/ansible/inventory/{environment}.yaml`
- Hosts file: `undercloud-deploy/{environment}/inventory/hosts.yaml`
- Group vars: `undercloud-deploy/{environment}/inventory/group_vars/*.yaml`

**For local development convenience**, you can copy all inventory files into a single directory and mount that:

```bash
# Create a local inventory directory
mkdir -p /tmp/my-inventory

# Copy all inventory files
cp /path/to/undercloud-deploy/ansible/inventory/uc-iad3-dev.yaml /tmp/my-inventory/
cp /path/to/undercloud-deploy/bravo-uc-iad3-dev/inventory/hosts.yaml /tmp/my-inventory/
cp -r /path/to/undercloud-deploy/bravo-uc-iad3-dev/inventory/group_vars /tmp/my-inventory/

# Mount the consolidated directory
-v /tmp/my-inventory:/runner/inventory
```

Example environment paths:

- Dev: `/path/to/undercloud-deploy/bravo-uc-iad3-dev/inventory`
- Staging: `/path/to/undercloud-deploy/charlie-uc-iad3-staging/inventory`

## Using Different Container Tags

### Latest Release

```bash
ghcr.io/rackerlabs/understack/ansible:latest
```

### Specific PR (for testing)

```bash
ghcr.io/rackerlabs/understack/ansible:pr-862
```

## Troubleshooting

### Check Container Contents

```bash
docker run --rm -it ghcr.io/rackerlabs/understack/ansible:latest bash
ls -la /runner/project/
```

### View Ansible Version

```bash
docker run --rm -it ghcr.io/rackerlabs/understack/ansible:latest \
  ansible --version
```

### Test OpenStack Connectivity

```bash
docker run --rm -it \
  -e OS_USERNAME=admin \
  -e OS_PASSWORD=your_password \
  -e OS_PROJECT_NAME=admin \
  -e OS_AUTH_URL=https://keystone.example.com/v3 \
  -e OS_USER_DOMAIN_NAME=Default \
  -e OS_PROJECT_DOMAIN_NAME=Default \
  ghcr.io/rackerlabs/understack/ansible:latest \
  bash -c "openstack --version && openstack token issue"
```

## Building the Container Locally

To build the container from source:

```bash
docker build -f containers/ansible/Dockerfile -t understack-ansible:local .
```

Then use your local image:

```bash
docker run --rm -it understack-ansible:local ansible-runner run /runner --playbook your-playbook.yaml
```
