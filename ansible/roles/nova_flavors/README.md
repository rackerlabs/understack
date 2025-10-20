# Nova Flavors Ansible Role

This role creates and manages OpenStack Nova flavors based on UnderStack flavor and device-type definitions stored in ConfigMaps.

## Purpose

The `nova_flavors` role automates the creation of Nova flavors for bare metal provisioning by:

1. Reading flavor definitions from the `flavors` ConfigMap
2. Reading device-type definitions from the `device-types` ConfigMap
3. Matching flavor resource classes to device-type resource class specifications
4. Creating Nova flavors with properties derived from device-types
5. Configuring scheduling constraints using resource classes and traits

See the [UnderStack Flavors Design Guide](https://rackerlabs.github.io/understack/design-guide/flavors/) for architectural details.

## How It Works

### Example

**Flavor Definition** (`m1.small.nicX.yaml`):

```yaml
name: m1.small.nicX
resource_class: m1.small
traits:
  - trait: NICX
    state: required
```

**Device-Type Definition** (`dell-poweredge-r7615.yaml`):

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

**Resulting Nova Flavor**:

- **Name**: `m1.small.nicX`
- **vCPUs**: 16 (from device-type cpu.cores)
- **RAM**: 131072 MB (from device-type memory.size)
- **Disk**: 480 GB (from device-type drives[0].size)
- **Extra Specs**:
  - `resources:VCPU='0'` - bare metal doesn't consume virtual CPU
  - `resources:MEMORY_MB='0'` - bare metal doesn't consume virtual memory
  - `resources:DISK_GB='0'` - bare metal doesn't consume virtual disk
  - `resources:CUSTOM_M1_SMALL='1'` - requires one bare metal node of this resource class
  - `trait:CUSTOM_NICX='required'` - requires the NICX trait

This matches the [OpenStack Ironic flavor configuration pattern](https://docs.openstack.org/ironic/latest/install/configure-nova-flavors.html) where the resource class is prefixed with `CUSTOM_`.

## Requirements

### Collections

- `openstack.cloud` - for `compute_flavor` module
- `community.general` - for `filetree` lookup plugin

### ConfigMaps

The role expects two ConfigMaps to be mounted in the container:

1. **flavors** ConfigMap mounted at `/runner/data/flavors/`
   - Contains flavor YAML definitions
   - Generated from `$UC_DEPLOY/hardware/flavors/`

2. **device-types** ConfigMap mounted at `/runner/data/device-types/`
   - Contains device-type YAML definitions
   - Generated from `$UC_DEPLOY/hardware/device-types/`

### OpenStack Authentication

The role uses the `openstack.cloud.compute_flavor` module which requires OpenStack credentials configured in one of these ways:

- `clouds.yaml` file in standard locations (`/etc/openstack/`, `~/.config/openstack/`)
- Environment variables (`OS_CLOUD`, `OS_AUTH_URL`, `OS_USERNAME`, etc.)

## Role Variables

### Required Variables

None - the role works with default values if ConfigMaps are properly mounted.

### Optional Variables

```yaml
# OpenStack cloud configuration name from clouds.yaml
openstack_cloud: default

# Path to flavors ConfigMap data
flavors_configmap_path: /runner/data/flavors/

# Path to device-types ConfigMap data
device_types_configmap_path: /runner/data/device-types/

# Async job timeout in seconds
flavor_creation_timeout: 300

# Async job polling settings
flavor_async_retries: 30
flavor_async_delay: 5
```

## Dependencies

None

## Example Playbook

```yaml
---
- name: Create Nova flavors from UnderStack definitions
  hosts: localhost
  gather_facts: false
  roles:
    - role: nova_flavors
      vars:
        openstack_cloud: understack
```

## Task Breakdown

### main.yml

1. **Collect flavor definitions** - reads all YAML files from `/runner/data/flavors/`
2. **Collect device-type definitions** - reads all YAML files from `/runner/data/device-types/`
3. **Build resource_class mapping** - creates a lookup table mapping resource class names to their CPU/memory/disk specs
4. **Loop through flavors** - processes each flavor definition
5. **Wait for async jobs** - waits for all flavor creation tasks to complete

### nova_flavors.yml

For each flavor:

1. **Lookup resource specs** - finds the device-type resource class specifications
2. **Build trait requirements** - extracts required and forbidden traits, adds `CUSTOM_` prefix
3. **Build base extra_specs** - creates resource consumption specs (always 0 for bare metal) and resource class requirement
4. **Build trait extra_specs** - adds trait requirements (`required` or `forbidden`)
5. **Combine extra_specs** - merges all scheduling constraints
6. **Create Nova flavor** - calls `openstack.cloud.compute_flavor` with derived properties
7. **Track async job** - stores job ID for later status checking

## Trait Handling

The role automatically adds the `CUSTOM_` prefix to trait names:

**Flavor definition**:

```yaml
traits:
  - trait: NICX
    state: required
  - trait: GPU
    state: absent
```

**Resulting extra_specs**:

```yaml
trait:CUSTOM_NICX: required
trait:CUSTOM_GPU: forbidden
```

This matches the [OpenStack trait naming convention](https://docs.openstack.org/placement/latest/user/index.html#traits) where custom traits must have the `CUSTOM_` prefix.

## Resource Class Naming

Resource class names are normalized to uppercase with special characters replaced by underscores:

- `m1.small` → `CUSTOM_M1_SMALL`
- `compute-gpu` → `CUSTOM_COMPUTE_GPU`
- `storage_nvme` → `CUSTOM_STORAGE_NVME`

This ensures valid extra_spec keys for OpenStack placement.

## Error Handling

The role will fail if:

- A flavor references a non-existent resource class (not found in any device-type)
- Required ConfigMaps are not mounted at expected paths
- OpenStack authentication fails
- Flavor creation fails (invalid parameters, permissions, etc.)

Error messages will indicate which flavor and resource class caused the failure.

## Testing

To test the role locally:

1. Prepare test data directories:
```bash
mkdir -p /tmp/test-data/flavors /tmp/test-data/device-types
cp examples/deploy-repo/hardware/flavors/*.yaml /tmp/test-data/flavors/
cp examples/deploy-repo/hardware/device-types/*.yaml /tmp/test-data/device-types/
```

2. Create a test playbook:
```yaml
---
- name: Test nova_flavors role
  hosts: localhost
  gather_facts: false
  roles:
    - role: nova_flavors
      vars:
        flavors_configmap_path: /tmp/test-data/flavors/
        device_types_configmap_path: /tmp/test-data/device-types/
        openstack_cloud: devstack
```

3. Run the playbook:
```bash
ansible-playbook test-nova-flavors.yml
```

## Integration with UnderStack

This role is part of the UnderStack flavor management workflow:

1. **Define flavors** - operators create flavor YAML files using `understackctl flavor add`
2. **GitOps deployment** - ArgoCD syncs flavor definitions to ConfigMaps
3. **Trigger workflow** - flavor ConfigMap changes trigger Argo Workflow
4. **Execute role** - Argo Workflow runs ansible playbook with this role
5. **Create flavors** - Nova flavors are created/updated in OpenStack
6. **User scheduling** - users select flavors when launching instances

See the [Flavors Operator Guide](https://rackerlabs.github.io/understack/operator-guide/flavors/) for the complete workflow.

## License

Apache 2.0

## Author Information

UnderStack Team - https://github.com/rackerlabs/understack
