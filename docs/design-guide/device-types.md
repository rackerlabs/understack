# Device Types

Device types provide a structured way to define and categorize hardware models
supported by UnderStack. They serve as a declarative specification of hardware
characteristics, enabling consistent hardware identification, resource class
mapping, and infrastructure automation across the platform.

## Purpose and Architecture

Device type definitions solve several critical challenges in bare metal
infrastructure management:

* **Hardware Identification**: Precise specification of manufacturer, model,
  and physical attributes enables automated detection and categorization
* **Resource Classification**: Multiple resource class configurations per
  device type allow flexible mapping of the same hardware model to different
  Nova flavors and workload profiles
* **Infrastructure as Code**: Hardware specifications live in Git alongside
  deployment configurations, providing versioning, review, and audit capabilities
* **Cross-Platform Integration**: Device types integrate with Nautobot,
  Ironic, and Nova to provide consistent hardware metadata throughout the stack

## Schema Structure

Device type definitions follow the [device-type.schema.json](https://github.com/rackerlabs/understack/blob/main/schema/device-type.schema.json)
JSON Schema, which enforces validation and consistency across all definitions.

### Core Properties

All device types must specify:

* **class**: Device category - `server`, `switch`, or `firewall`
* **manufacturer**: Hardware vendor (e.g., "Dell", "HPE")
* **model**: Specific model identifier (e.g., "PowerEdge R7615")
* **u_height**: Rack unit height (must be greater than 0)
* **is_full_depth**: Boolean indicating full-depth rack mounting

### Optional Properties

Device types may include:

* **interfaces**: Named physical network interfaces on the hardware. Used to
  define specific ports such as management interfaces (BMC/iDRAC/iLO) or
  named switch ports. Each interface has:
    * `name`: Interface identifier (e.g., "iDRAC", "eth0", "mgmt")
    * `type`: Physical interface type (e.g., "1000base-t", "10gbase-x-sfp+")
    * `mgmt_only`: Boolean flag indicating management-only interfaces
* **resource_class**: Array of resource class configurations (required for
  `class: server`)

### Resource Classes

For server-class devices, resource classes define the specific hardware
configurations that map to OpenStack Nova flavors. Multiple resource classes
can be defined for the same hardware model to represent common build
configurations in the data center (e.g., different CPU, RAM, or drive
populations of the same chassis).

During server enrollment, the hardware inspection data is matched against
these resource class definitions. The matching resource class name is set on
the Ironic node's `resource_class` property, which is then used to create
corresponding Nova flavors for workload scheduling.

Each resource class requires:

* **name**: Resource class identifier (e.g., "m1.small", "compute-optimized").
  This value will be set on the Ironic node and used for Nova flavor creation.
* **cpu**: Object with `cores` (number) and `model` (string)
* **memory**: Object with `size` in GB
* **drives**: Array of drive objects, each with `size` in GB
* **nic_count**: Minimum number of user-usable network interfaces (integer).
  This represents general-purpose network ports available for workload traffic,
  not tied to specific named interfaces. Used to verify the server has
  sufficient network connectivity for the workload profile.

## Example Definition

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/device-type.schema.json
class: server
manufacturer: Dell
model: PowerEdge R7615
u_height: 2
is_full_depth: true

# Named physical interfaces (management, specific ports)
interfaces:
  - name: iDRAC
    type: 1000base-t
    mgmt_only: true

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
    # User-usable network interfaces (not tied to specific named ports)
    nic_count: 2
```

## Integration Points

### GitOps Deployment

Device type definitions live in the deployment repository under
`hardware/device-types/`. They are packaged as Kubernetes ConfigMaps via
Kustomize, making them available to platform components.

### Resource Class Matching and Nova Flavors

During bare metal enrollment:

1. Hardware is inspected via Ironic to collect CPU, memory, drive, and network
   interface data
2. The `understack-flavor-matcher` service compares inspection data against
   device type resource class definitions
3. When a match is found, the resource class name is set on the Ironic node's
   `resource_class` property
4. Nova flavors are created or updated based on the resource class, making the
   hardware available for workload scheduling

**Multiple Resource Classes**: Define multiple resource classes for the same
device type when you have common build variations of the same chassis. For
example, a Dell PowerEdge R7615 might be populated with different CPU models,
RAM capacities, or drive configurations depending on the intended workload
(compute, storage, memory-intensive, etc.).

### Nautobot Synchronization

Device types provide the source of truth for hardware specifications that are
synchronized to Nautobot's device type models, ensuring consistency between
the deployment repository and the infrastructure CMDB.

### Ironic Integration

During bare metal enrollment and inspection, Ironic driver metadata is
validated against device type definitions to confirm hardware matches
expected specifications.

## File Organization

Device type definitions are organized in the deployment repository:

```text
hardware/
├── base/
│   └── kustomization.yaml          # ConfigMap generation
└── device-types/
    ├── dell-poweredge-r7615.yaml
    ├── hpe-proliant-dl360.yaml
    └── ...
```

The `base/kustomization.yaml` generates a ConfigMap containing all device
type definitions:

```yaml
configMapGenerator:
  - name: device-types
    options:
      disableNameSuffixHash: true
    files:
      - dell-poweredge-r7615.yaml=../device-types/dell-poweredge-r7615.yaml
```

## Schema Validation

Device type files include a YAML language server directive for editor-based
validation:

```yaml
# yaml-language-server: $schema=https://rackerlabs.github.io/understack/device-type.schema.json
```

The schema enforces:

* Required field presence
* Type correctness (strings, numbers, booleans, arrays, objects)
* Enum constraints (e.g., `class` must be server/switch/firewall)
* Conditional requirements (servers must have resource classes)
* Numeric constraints (e.g., `u_height > 0`)

## Management Workflow

Device types are managed through the `understackctl` CLI tool:

**Adding new device types:**

1. Create new device type definitions as YAML files
2. Validate and add with `understackctl device-type add <file>` (automatically updates Kustomization)
3. Commit to Git and submit pull request
4. ArgoCD detects changes and updates ConfigMap
5. Platform components consume updated definitions

**Updating existing device types:**

1. Edit the device type file in `$UC_DEPLOY/hardware/device-types/`
2. Validate with `understackctl device-type validate <file>`
3. Commit to Git and submit pull request
4. ArgoCD detects changes and updates ConfigMap

See the [operator guide](../operator-guide/device-types.md) for detailed
command usage and examples.
