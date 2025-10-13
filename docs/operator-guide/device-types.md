# Device Type Management

Device types define the hardware models supported by your UnderStack
deployment. This guide covers how to create, manage, and validate device
type definitions using the `understackctl` CLI tool.

For architectural details and schema information, see the
[design guide](../design-guide/device-types.md).

## Prerequisites

* `understackctl` CLI tool installed
* Access to your deployment repository
* `UC_DEPLOY` environment variable set to your deployment repository path

## Command Overview

The `understackctl device-type` command provides five subcommands:

```bash
understackctl device-type add <file>      # Add a device type to the deployment
understackctl device-type validate <file> # Validate a device type definition
understackctl device-type delete <name>   # Delete a device type
understackctl device-type list            # List all device types
understackctl device-type show <name>     # Show device type details
```

All commands require the `UC_DEPLOY` environment variable to be set:

```bash
export UC_DEPLOY=/path/to/your/deployment-repo
```

## Creating Device Type Definitions

### 1. Create the YAML Definition File

Create a new YAML file with your hardware specifications. You can create it
anywhere (e.g., `/tmp/my-device.yaml`). The filename doesn't matter at this
stage as it will be automatically named based on the manufacturer and model
when added to the deployment.

### 2. Define the Hardware Specification

Start with the YAML language server directive for editor validation:

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/device-type.schema.json
class: server
manufacturer: Dell
model: PowerEdge R7615
u_height: 2
is_full_depth: true
```

### 3. Add Network Interfaces

Define named physical interfaces on the hardware. This is typically used for
management interfaces (BMC/iDRAC/iLO) or specific named ports on network
devices:

```yaml
interfaces:
  - name: iDRAC
    type: 1000base-t
    mgmt_only: true
```

**Note**: General-purpose network ports for workload traffic are specified
using `nic_count` in the resource class definition, not here.

### 3a. Add Power Ports (Optional)

Define power inlet specifications for accurate power capacity planning and
monitoring:

```yaml
power-ports:
  - name: psu1
    type: iec-60320-c14
    maximum_draw: 750
  - name: psu2
    type: iec-60320-c14
    maximum_draw: 750
```

Each power port specification includes:

* `name`: Power supply identifier (e.g., "psu1", "psu2", "PSU-A")
* `type`: Power connector type - see [Nautobot PowerPortTypeChoices](https://github.com/nautobot/nautobot/blob/develop/nautobot/dcim/choices.py#L507) for valid values (e.g., "iec-60320-c14", "iec-60320-c20")
* `maximum_draw`: Maximum power draw in watts (optional)

Common power port types:

* `iec-60320-c14`: Standard 15A power inlet (most common for servers)
* `iec-60320-c20`: High-current 20A power inlet (used for high-power servers)
* `iec-60309-p-n-e-6h`: Industrial 3-phase power connectors

**Note**: Power port information helps with capacity planning and can be
synchronized to Nautobot for power feed calculations.

### 4. Define Resource Classes

For server-class devices, specify one or more resource class configurations.
Each resource class represents a hardware profile that can be matched to
servers during enrollment:

```yaml
resource_class:
  - name: m1.small
    cpu:
      cores: 16
      model: AMD EPYC 9124
    memory:
      size: 128
    drives:
      - size: 480
      - size: 480
    # Minimum user-usable network interfaces (not tied to specific named ports)
    nic_count: 2

  - name: m1.medium
    cpu:
      cores: 32
      model: AMD EPYC 9334
    memory:
      size: 256
    drives:
      - size: 960
      - size: 960
    # This configuration requires at least 2 network ports for workload traffic
    nic_count: 2
```

**Understanding nic_count**: This field specifies the minimum number of
general-purpose network interfaces available for workload traffic. These are
not tied to specific named interfaces defined in the top-level `interfaces`
section. The system verifies that the server has at least this many usable
network ports beyond any management-only interfaces.

**Understanding multiple resource classes**: You can define multiple resource
classes for the same device type to represent different hardware configurations
of the same chassis model. For example, you might populate the same server
model with different CPU, RAM, or storage configurations depending on the
intended workload. Each resource class represents one of these common build
variations in your data center. During hardware enrollment, the inspection
data is matched against these definitions, and the matching resource class
name is set on the Ironic node for Nova flavor creation.

### 5. Add to Deployment

Use the `add` command to validate and add your device type definition to the
deployment repository:

```bash
understackctl device-type add /tmp/dell-poweredge-r7615.yaml
```

The command will:

* Validate the YAML structure against the full JSON schema
* Check all required fields, types, and constraints
* Automatically generate a filename from manufacturer and model (lowercase with hyphens, e.g., `dell-poweredge-r7615.yaml`)
* Copy the file to `$UC_DEPLOY/hardware/device-types/`
* Update `$UC_DEPLOY/hardware/base/kustomization.yaml` to include the new device type

Successful output:

```text
INFO Device type added successfully path=$UC_DEPLOY/hardware/device-types/dell-poweredge-r7615.yaml
INFO Added to kustomization.yaml file=dell-poweredge-r7615.yaml
```

Validation errors will show which fields are missing or invalid:

```text
Error: missing required field: u_height
Error: device-type already exists at $UC_DEPLOY/hardware/device-types/dell-poweredge-r7615.yaml
```

### 6. Commit and Deploy

The kustomization file has been automatically updated by the `add` command.

```bash
cd $UC_DEPLOY
git add hardware/
git commit -m "Add Dell PowerEdge R7615 device type definition"
git push
```

ArgoCD will detect the changes and update the device-types ConfigMap.

## Validating Device Types

You can validate a device type definition without adding it to the deployment:

```bash
understackctl device-type validate /tmp/dell-poweredge-r7615.yaml
```

This performs full JSON schema validation including:

* Required field presence
* Type correctness (strings, numbers, booleans, arrays, objects)
* Enum constraints (e.g., `class` must be server/switch/firewall)
* Conditional requirements (servers must have resource classes)
* Numeric constraints (e.g., `u_height > 0`)

Successful output:

```text
INFO Device type definition is valid class=server manufacturer=Dell model=PowerEdge R7615
```

Validation errors will show the specific issue:

```text
Error: validation failed: u_height: must be > 0
Error: validation failed: missing properties: 'cpu', 'memory', 'drives', 'interfaces'
```

## Listing Device Types

View all device type definitions in your deployment:

```bash
understackctl device-type list
```

Example output:

```text
Device Types:
  - dell-poweredge-r7615
  - hpe-proliant-dl360
  - cisco-nexus-9336c
```

## Viewing Device Type Details

Display the full specification for a specific device type:

```bash
understackctl device-type show dell-poweredge-r7615
```

Example output:

```text
Device Type: dell-poweredge-r7615
═══════════════════════════════════════════

Class:        server
Manufacturer: Dell
Model:        PowerEdge R7615
Height (in u): 2
Full Depth:   true

Interfaces:
  1. iDRAC (1000base-t) [Management Only]

Resource Classes:

  1. m1.small
     ───────────────────────────────────
     CPU:    16 cores (AMD EPYC 9124)
     Memory: 128 GB
     NICs:   2
     Drives: 480 GB, 480 GB

  2. m1.medium
     ───────────────────────────────────
     CPU:    32 cores (AMD EPYC 9334)
     Memory: 256 GB
     NICs:   2
     Drives: 960 GB, 960 GB

  3. m1.large
     ───────────────────────────────────
     CPU:    64 cores (AMD EPYC 9554)
     Memory: 512 GB
     NICs:   4
     Drives: 1920 GB, 1920 GB
```

## Updating Device Types

To update an existing device type definition:

1. Edit the file directly in `$UC_DEPLOY/hardware/device-types/`
1. Validate your changes:

```bash
understackctl device-type validate $UC_DEPLOY/hardware/device-types/dell-poweredge-r7615.yaml
```

1. Commit the changes:

```bash
cd $UC_DEPLOY
git add hardware/device-types/dell-poweredge-r7615.yaml
git commit -m "Update Dell PowerEdge R7615 device type configuration"
git push
```

ArgoCD will detect the changes and update the device-types ConfigMap.

## Deleting Device Types

Remove a device type definition from your deployment:

```bash
understackctl device-type delete dell-poweredge-r7615
```

The command will:

* Remove the file from `$UC_DEPLOY/hardware/device-types/`
* Update `$UC_DEPLOY/hardware/base/kustomization.yaml` to remove the entry

After deletion, commit the changes:

```bash
cd $UC_DEPLOY
git add hardware/
git commit -m "Remove Dell PowerEdge R7615 device type"
git push
```

## Best Practices

### Naming Conventions

* Filenames are automatically generated from the manufacturer and model fields
* Ensure manufacturer and model fields are accurate as they determine the filename

### Resource Class Design

* Define resource classes that map to your Nova flavor strategy
* Use descriptive names that indicate the workload type or size tier
* Define multiple resource classes for the same device type when you have
  common build variations in your data center
* Resource class names are set on Ironic nodes and used to create Nova flavors

**Example**: A Dell PowerEdge R7615 chassis might have three common builds:

* `m1.small`: 16-core CPU, 128GB RAM, basic drives (general compute)
* `m1.medium`: 32-core CPU, 256GB RAM, faster drives (balanced workloads)
* `m1.large`: 64-core CPU, 512GB RAM, high-capacity drives (memory-intensive)

Each build variation becomes a separate resource class, allowing precise
matching during hardware enrollment and accurate Nova flavor creation.

### Version Control

* Always validate device types before committing
* Include descriptive commit messages explaining what hardware is being added
* Submit changes via pull requests for team review
* Tag releases when updating device type definitions for production deployments

### Interface Definitions

* Use the top-level `interfaces` section for named physical ports (management
  interfaces, specific switch ports)
* Mark management interfaces with `mgmt_only: true`
* Follow standard interface type naming (e.g., `1000base-t`, `10gbase-x-sfp+`,
  `25gbase-x-sfp28`) - see [Nautobot interface types](https://docs.nautobot.com/projects/core/en/stable/user-guide/core-data-model/dcim/interface/#interface-type) for available values
* Use `nic_count` in resource classes to specify minimum user-usable network
  ports (not tied to specific named interfaces)

## Troubleshooting

### Validation Failures

**Missing required fields**:

Ensure all required fields are present: `class`, `manufacturer`, `model`,
`u_height`, `is_full_depth`. For server-class devices, also include
`resource_class`.

**Invalid class value**:

The `class` field must be exactly one of: `server`, `switch`, `firewall`.

**Invalid u_height**:

The `u_height` must be a number greater than 0.

**Invalid resource class**:

Each resource class entry must include all required fields: `name`, `cpu`,
`memory`, `drives`, `nic_count`.

### ConfigMap Not Updating

If ArgoCD doesn't pick up your changes:

1. Verify the file is listed in `hardware/base/kustomization.yaml`
2. Check that you've committed and pushed to the correct branch
3. Review ArgoCD application status: `kubectl get applications -n argocd`
4. Force a sync if needed: `argocd app sync <application-name>`

### Schema Validation in Editor

If your editor doesn't validate the YAML:

1. Ensure the schema directive is on the first line
2. Verify your editor supports YAML language server protocol
3. Check that the schema URL is accessible
4. Try installing a YAML extension for your editor (e.g., YAML extension for
   VS Code)

## Examples

### Server Device Type

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/device-type.schema.json
class: server
manufacturer: HPE
model: ProLiant DL360 Gen10
u_height: 1
is_full_depth: true

interfaces:
  - name: iLO
    type: 1000base-t
    mgmt_only: true
  - name: NIC1
    type: 10gbase-x-sfp+
  - name: NIC2
    type: 10gbase-x-sfp+

power-ports:
  - name: psu1
    type: iec-60320-c14
    maximum_draw: 800
  - name: psu2
    type: iec-60320-c14
    maximum_draw: 800

resource_class:
  - name: compute-standard
    cpu:
      cores: 24
      model: Intel Xeon Gold 6252
    memory:
      size: 192
    drives:
      - size: 480
      - size: 960
      - size: 960
    nic_count: 2
```

### Switch Device Type

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/device-type.schema.json
class: switch
manufacturer: Cisco
model: Nexus 9336C-FX2
u_height: 1
is_full_depth: true

interfaces:
  - name: mgmt0
    type: 1000base-t
    mgmt_only: true
  - name: Ethernet1/1
    type: 100gbase-x-qsfp28
  - name: Ethernet1/2
    type: 100gbase-x-qsfp28
  # ... additional 34 100G QSFP28 ports

power-ports:
  - name: ps1
    type: iec-60320-c14
    maximum_draw: 450
  - name: ps2
    type: iec-60320-c14
    maximum_draw: 450
```

### Firewall Device Type

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/device-type.schema.json
class: firewall
manufacturer: Palo Alto
model: PA-5220
u_height: 3
is_full_depth: true

interfaces:
  - name: mgmt
    type: 1000base-t
    mgmt_only: true
  - name: ha1-a
    type: 1000base-t
  - name: ha1-b
    type: 1000base-t
  - name: ethernet1/1
    type: 10gbase-t
  - name: ethernet1/5
    type: 10gbase-x-sfp+
  # ... additional data plane interfaces

power-ports:
  - name: psu1
    type: iec-60320-c20
    maximum_draw: 1440
  - name: psu2
    type: iec-60320-c20
    maximum_draw: 1440
```
