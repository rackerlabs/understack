# Creating the Deploy Repo

A deployment of UnderStack includes many different services, some of
which will require specific configuration about your environment such
as details about the hardware you will use or details on how you will
connect to the hardware.

These details will be accumulated in your Deployment Repository with
some data being shared while most being scoped to a
[Global cluster](./welcome.md#system-division) or
a [Site cluster](./welcome.md#system-division).

## Initial Structure

To begin we will create our directory structure inside our Deployment Repository
using the `understackctl` CLI tool.

```bash title="From the Deployment Repo"
# For a global cluster
understackctl deploy init my-global --type global

# For a site cluster
understackctl deploy init my-site --type site

# For an all-in-one (AIO) cluster
understackctl deploy init my-aio --type aio
```

This creates a `deploy.yaml` configuration file with the component list for your
cluster type. The `deploy_url` will be auto-detected from your git remote if available.

Example `deploy.yaml` for a site cluster:

```yaml
understack_url: https://github.com/rackerlabs/understack.git
deploy_url: git@github.com:my-org/my-deploy.git
site:
  enabled: true
  keystone:
    enabled: true
  nova:
    enabled: true
  neutron:
    enabled: true
  ironic:
    enabled: true
  glance:
    enabled: true
  # ... additional site components
```

After initialization, create the manifest directories:

```bash
understackctl deploy update my-site
```

This creates `<component>/` directories with `kustomization.yaml` and
`values.yaml` files for each enabled component.

### component directories

Inside of the `manifests` directory you'll have child directories named after
each component (using hyphens, e.g., `cert-manager`, `argo-workflows`). These
directories contain:

- `kustomization.yaml` - Kustomize configuration for the component
- `values.yaml` - Helm value overrides for the component

You can verify all required files exist with:

```bash
understackctl deploy check my-site
```

### Managing Components

To enable or disable components, edit the component sections in `deploy.yaml`:

```yaml
site:
  enabled: true
  keystone:
    enabled: true
  nova:
    enabled: true
  neutron:
    enabled: false  # Disable by setting to false
```

Then sync the filesystem:

```bash
understackctl deploy update my-site
```

This will create directories for enabled components and remove directories for
disabled components.

!!! note "Component Naming"
    Component names in `deploy.yaml` use underscores (e.g., `cert_manager`,
    `argo_workflows`) but the corresponding directories use hyphens
    (e.g., `cert-manager`, `argo-workflows`). The `understackctl` tool
    handles this conversion automatically.

### inventory directory

This directory contains an Ansible inventory file along with Ansible
group_vars that are used as data by Ansible executions within the cluster
to configure different services

This directory contains an Ansible inventory file along with Ansible
group_vars that are used as data by Ansible executions within the cluster
to configure different services.
