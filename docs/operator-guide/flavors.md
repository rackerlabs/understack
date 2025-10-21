# Flavor Management

Flavors define how Ironic bare metal nodes are matched to Nova flavors based on resource classes and hardware traits. This guide covers how to create, manage, and validate flavor definitions using the `understackctl` CLI tool.

For architectural details and integration information, see the [design guide](../design-guide/flavors.md).

## Prerequisites

* `understackctl` CLI tool installed
* Access to your deployment repository
* `UC_DEPLOY` environment variable set to your deployment repository path
* Existing device-type definitions with resource classes

## Command Overview

The `understackctl flavor` command provides five subcommands:

```bash
understackctl flavor add <file>      # Add a flavor to the deployment
understackctl flavor validate <file> # Validate a flavor definition
understackctl flavor delete <name>   # Delete a flavor
understackctl flavor list            # List all flavors
understackctl flavor show <name>     # Show flavor details
```

All commands require the `UC_DEPLOY` environment variable to be set:

```bash
export UC_DEPLOY=/path/to/your/deployment-repo
```

## Creating Flavor Definitions

### 1. Create the YAML Definition File

Create a new YAML file with your flavor specification. You can create it anywhere (e.g., `/tmp/my-flavor.yaml`). The filename doesn't matter at this stage as it will be automatically named based on the flavor name when added to the deployment.

### 2. Define the Flavor Specification

Start with the YAML language server directive for editor validation:

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/schema/flavor.schema.json
name: m1.small
resource_class: m1.small
description: Small compute flavor with 16 cores, 128GB RAM, and dual 480GB drives
```

**Required Fields**:

* `name`: Unique flavor name (e.g., `m1.small`, `compute.standard`)
* `resource_class`: Must match a resource class defined in a device-type

**Optional Fields**:

* `description`: Human-readable description shown in Nova flavor details
* `traits`: Hardware trait requirements for filtering nodes (see below)

**Note**: Nova flavor properties (vCPUs, RAM, disk) are automatically derived from the device-type resource class specification for convenience. Nova performs scheduling by matching the resource class and traits on Ironic nodes. See the [OpenStack Ironic flavor configuration documentation](https://docs.openstack.org/ironic/latest/install/configure-nova-flavors.html) for details.

### 3. Add Optional Description and Trait Requirements

Add a description and/or hardware trait requirements to filter which nodes match this flavor:

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/schema/flavor.schema.json
name: m1.small.nicX
resource_class: m1.small
description: Small compute flavor with NICX network hardware - 16 cores, 128GB RAM, dual 480GB drives
traits:
  - trait: NICX
    state: required
```

**Trait Requirements**:

* `trait`: Hardware trait name WITHOUT the `CUSTOM_` prefix (e.g., `NICX`, `GPU`, `NVME`)
    * Must be uppercase alphanumeric with underscores
    * The system automatically adds `CUSTOM_` prefix when interacting with Ironic
* `state`: Either `required` (node must have trait) or `absent` (node must not have trait)

### 4. Add to Deployment

Use the `add` command to validate and add your flavor definition to the deployment repository:

```bash
understackctl flavor add /tmp/m1.small.yaml
```

The command will:

* Validate the YAML structure against the full JSON schema
* Check all required fields and types
* Automatically generate a filename from the flavor name (e.g., `m1.small.yaml`)
* Copy the file to `$UC_DEPLOY/hardware/flavors/`
* Update `$UC_DEPLOY/hardware/base/kustomization.yaml` to include the new flavor

Successful output:

```text
INFO Flavor added successfully path=$UC_DEPLOY/hardware/flavors/m1.small.yaml
INFO Added to kustomization.yaml file=m1.small.yaml
```

Validation errors will show which fields are missing or invalid:

```text
Error: validation failed: missing properties: 'resource_class'
Error: flavor already exists at $UC_DEPLOY/hardware/flavors/m1.small.yaml
```

### 5. Commit and Deploy

The kustomization file has been automatically updated by the `add` command.

```bash
cd $UC_DEPLOY
git add hardware/
git commit -m "Add m1.small flavor definition"
git push
```

ArgoCD will detect the changes and update the flavors ConfigMap.

### Automatic Nova Flavor Synchronization

After the ConfigMaps are updated, UnderStack automatically synchronizes Nova flavors:

1. **ConfigMap Update**: ArgoCD syncs the `flavors` and `device-types` ConfigMaps
2. **Workflow Trigger**: A post-deployment workflow runs after Nova is deployed
3. **Flavor Sync**: The workflow reads both ConfigMaps and creates/updates Nova flavors with:
   * Properties (vcpus, ram, disk) derived from device-type resource class specs
   * Extra specs for Ironic bare metal scheduling:
     * `resources:VCPU=0`
     * `resources:MEMORY_MB=0`
     * `resources:DISK_GB=0`
     * `resources:CUSTOM_{RESOURCE_CLASS}=1`
   * Trait requirements (if specified in flavor definition)
4. **Verification**: Check that flavors were created:

```bash
openstack --os-cloud understack flavor list
openstack --os-cloud understack flavor show m1.small -f yaml
```

The flavor synchronization runs automatically whenever:

* Nova is deployed/redeployed
* Flavor ConfigMap is updated
* Device-type ConfigMap is updated

No manual intervention is required - the system maintains Nova flavors in sync with your GitOps definitions.

## Validating Flavors

You can validate a flavor definition without adding it to the deployment:

```bash
understackctl flavor validate /tmp/m1.small.yaml
```

This performs full JSON schema validation including:

* Required field presence (name, resource_class)
* Type correctness (strings)
* Trait name patterns (uppercase alphanumeric with underscores)
* Trait state enum values (`required` or `absent`)

Successful output:

```text
INFO Flavor definition is valid name=m1.small resource_class=m1.small
```

Validation errors will show the specific issue:

```text
Error: validation failed: traits[0].state: must be one of [required, absent]
Error: validation failed: traits[0].trait: does not match pattern ^[A-Z][A-Z0-9_]*$
```

## Listing Flavors

View all flavor definitions in your deployment:

```bash
understackctl flavor list
```

Example output:

```text
Flavors:
  - m1.small
  - m1.small.nicX
  - m1.medium
  - compute.gpu
```

## Viewing Flavor Details

Display the full specification for a specific flavor:

```bash
understackctl flavor show m1.small
```

Example output:

```text
Flavor: m1.small
═══════════════════════════════════════════

Resource Class: m1.small
  (Nova properties derived from device-type for convenience; scheduling uses resource class and traits)

Trait Requirements: None (matches all nodes in resource class)
```

For a flavor with trait requirements:

```text
Flavor: m1.small.nicX
═══════════════════════════════════════════

Resource Class: m1.small
  (Nova properties derived from device-type for convenience; scheduling uses resource class and traits)

Trait Requirements:
  1. NICX [required]
```

## Updating Flavors

To update an existing flavor definition:

1. Edit the file directly in `$UC_DEPLOY/hardware/flavors/`
1. Validate your changes:

```bash
understackctl flavor validate $UC_DEPLOY/hardware/flavors/m1.small.yaml
```

1. Commit the changes:

```bash
cd $UC_DEPLOY
git add hardware/flavors/m1.small.yaml
git commit -m "Update m1.small flavor trait requirements"
git push
```

ArgoCD will detect the changes and update the flavors ConfigMap.

## Deleting Flavors

Remove a flavor definition from your deployment:

```bash
understackctl flavor delete m1.small
```

The command will:

* Remove the file from `$UC_DEPLOY/hardware/flavors/`
* Update `$UC_DEPLOY/hardware/base/kustomization.yaml` to remove the entry

After deletion, commit the changes:

```bash
cd $UC_DEPLOY
git add hardware/
git commit -m "Remove m1.small flavor"
git push
```

## Common Use Cases

### Generic Hardware Flavor

Match all nodes in a resource class without trait filtering:

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/schema/flavor.schema.json
name: compute.standard
resource_class: m1.medium
```

This provides maximum flexibility by allowing any hardware in the `m1.medium` resource class.

### Specialized Hardware Flavor

Require specific hardware capabilities:

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/schema/flavor.schema.json
name: compute.gpu
resource_class: m1.large
traits:
  - trait: GPU
    state: required
```

Guarantees instances get nodes with GPU hardware.

### NIC-Specific Hardware

Require specific network hardware:

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/schema/flavor.schema.json
name: m1.small.mellanox-cx5
resource_class: m1.small
traits:
  - trait: NIC_MELLANOX_CX5
    state: required
```

Only matches nodes with Mellanox ConnectX-5 network cards.

### Multiple Traits

Combine multiple trait requirements:

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/schema/flavor.schema.json
name: compute.nvme-no-gpu
resource_class: m1.medium
traits:
  - trait: NVME
    state: required
  - trait: GPU
    state: absent
```

Requires NVMe storage but excludes GPU nodes.

## Best Practices

### Naming Conventions

* **Generic flavors**: Use simple, descriptive names (e.g., `compute.standard`, `m1.small`)
* **Specialized flavors**: Append trait indicators (e.g., `m1.small.mellanox-cx5`, `compute.gpu`)
* **Exclusion flavors**: Use descriptive suffixes (e.g., `m1.small.no-gpu`)

### Resource Class References

* Always ensure the `resource_class` exists in device-type definitions before creating flavors
* Use `understackctl device-type list` to see available resource classes
* Nova properties (vCPUs, RAM, disk) are automatically derived from the device-type resource class for convenience (scheduling uses resource class and traits)

### Trait Management

* Write trait names without the `CUSTOM_` prefix (it's added automatically)
* Use uppercase with underscores (e.g., `NICX`, `NVIDIA_A100`, `NVME_STORAGE`)
* Document trait meanings and discovery logic in your team's documentation
* Balance between specificity and flexibility (too many specific traits fragment hardware pools)

### Version Control

* Always validate flavors before committing
* Include descriptive commit messages explaining the purpose of the flavor
* Submit changes via pull requests for team review
* Test flavor matching in non-production before promoting to production

### Trait Strategy

* Create a base generic flavor for each resource class (e.g., `m1.small`)
* Add specialized variants only when users need guaranteed hardware features
* Use trait absence requirements sparingly (mainly for excluding known-problematic hardware)
* Document trait requirements in flavor names or commit messages

## Troubleshooting

### Validation Failures

**Missing required fields**:

Ensure both `name` and `resource_class` are present in the definition.

**Invalid trait name**:

Trait names must be uppercase alphanumeric with underscores. Don't include the `CUSTOM_` prefix.

**Invalid state**:

The `state` field must be exactly `required` or `absent`.

### ConfigMap Not Updating

If ArgoCD doesn't pick up your changes:

1. Verify the file is listed in `hardware/base/kustomization.yaml`
2. Check that you've committed and pushed to the correct branch
3. Review ArgoCD application status: `kubectl get applications -n argocd`
4. Force a sync if needed: `argocd app sync <application-name>`

### Resource Class Not Found

If the flavor references a non-existent resource class:

1. List available device-types: `understackctl device-type list`
2. Show device-type details to see resource classes: `understackctl device-type show <device-type-name>`
3. Create the necessary device-type or use an existing resource class

### Trait Matching Issues

If nodes aren't matching the expected flavor:

1. Check Ironic node traits: `openstack baremetal node show <node> -f json -c traits`
2. Verify trait names have the `CUSTOM_` prefix in Ironic
3. Confirm inspection code is properly adding traits to nodes
4. Review flavor-matcher logs for matching errors

### Schema Validation in Editor

If your editor doesn't validate the YAML:

1. Ensure the schema directive is on the first line
2. Verify your editor supports YAML language server protocol
3. Try installing a YAML extension for your editor (e.g., YAML extension for VS Code)

## Examples

### Generic Compute Flavor

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/schema/flavor.schema.json
name: m1.small
resource_class: m1.small
```

Matches all nodes in the `m1.small` resource class.

### NIC-Specific Flavor

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/schema/flavor.schema.json
name: m1.small.nicX
resource_class: m1.small
traits:
  - trait: NICX
    state: required
```

Only matches nodes with the `CUSTOM_NICX` trait.

### GPU Compute Flavor

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/schema/flavor.schema.json
name: compute.gpu
resource_class: m1.large
traits:
  - trait: GPU
    state: required
```

Guarantees GPU hardware for compute workloads.

### Combined Hardware Requirements

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/schema/flavor.schema.json
name: m1.medium.mellanox-cx5-nvme
resource_class: m1.medium
traits:
  - trait: NIC_MELLANOX_CX5
    state: required
  - trait: NVME
    state: required
```

Requires both Mellanox ConnectX-5 and NVMe storage.

## Integration with Device-Types

Flavors and device-types work together to define Nova flavors:

**Device-Type** (`dell-poweredge-r7615.yaml`):

```yaml
class: server
manufacturer: Dell
model: PowerEdge R7615
resource_class:
  - name: m1.small
    cpu:
      cores: 16
      model: AMD EPYC 9124
    memory:
      size: 131072  # MB (128 GB)
    drives:
      - size: 480  # GB
      - size: 480
    nic_count: 2
```

**Flavor** (`m1.small.yaml`):

```yaml
name: m1.small
resource_class: m1.small
```

The flavor-matcher service:

1. Reads the flavor definition
2. Queries Ironic for nodes with `resource_class=m1.small`
3. Looks up the device-type `m1.small` resource class
4. Creates a Nova flavor with:
    * vcpus: 16 (from `cpu.cores`)
    * ram: 131072 MB (from `memory.size`)
    * disk: 480 GB (from `drives[0].size`)

This separation allows you to:

* Define hardware specifications once in device-types
* Create multiple flavors (generic, specialized, exclusion) for the same resource class
* Filter hardware matching without duplicating Nova property specifications
