# Neutron Router Flavors Ansible Role

This role provides **idempotent management** of OpenStack Neutron router flavors and service profiles. It replaces the previous shell script approach with a robust, repeatable Ansible implementation.

## Purpose

The `neutron_router_flavors` role automates the creation and configuration of router flavors by:

1. Creating service profiles with driver definitions
2. Creating router flavors with appropriate metadata
3. Binding service profiles to flavors
4. Ensuring idempotent operations (safe to run repeatedly)
5. Verifying all configurations are in place

## Key Features

- **Idempotent**: Safe to run multiple times without side effects
- **Configurable**: Define flavors in site-config, not in code
- **Verifiable**: Validates all configurations are correct
- **Error Handling**: Retries on transient failures, clear error messages
- **Logging**: Debug output for troubleshooting

## Router Flavors

This role creates **five router flavors** by default:

| Flavor | Driver | VNI Mode | Purpose |
|--------|--------|----------|---------|
| `dynamic_vrf` | `neutron_understack.l3_router.vrf.Vrf` | `auto` | Fabric VRF with auto-allocated VXLAN VNI |
| `static_vrf` | `neutron_understack.l3_router.vrf.Vrf` | `on` | Fabric VRF with admin-supplied VNI |
| `svi` | `neutron_understack.l3_router.svi.Svi` | `off` | On-fabric SVI gateway routing |
| `cisco-asa` | `neutron_understack.l3_router.cisco_asa.CiscoAsa` | `off` | Physical Cisco ASA appliance |
| `palo-alto` | `neutron_understack.l3_router.palo_alto.PaloAlto` | `off` | Physical Palo Alto appliance |

## Requirements

### Collections
- `community.general` - for retries and filters
- `ansible.builtin` - core modules

### OpenStack
- OpenStack credentials configured in `clouds.yaml`
- `openstack` CLI tool available
- Neutron API accessible

### Ansible
- Ansible 2.9+
- `openstack.cloud` collections available

## Role Variables

### Required Variables

None - the role works with defaults if OpenStack credentials are configured.

### Optional Variables

```yaml
# OpenStack cloud configuration name from clouds.yaml
openstack_cloud: "{{ lookup('env', 'OS_CLOUD') | default('default') }}"

# Service type for router flavors
neutron_router_flavor_service_type: L3_ROUTER_NAT

# Router flavors configuration (see examples below)
neutron_router_flavors:
  - name: dynamic_vrf
    description: "Fabric VRF with auto-allocated VNI"
    driver: "neutron_understack.l3_router.vrf.Vrf"
    driver_description: "VRF Stub"
    service_profile_metainfo:
      vni_alloc: "auto"
    enabled: true
  # ... more flavors ...

# Retry settings for transient failures
neutron_router_flavor_retries: 3
neutron_router_flavor_delay: 5

# Command timeout
neutron_router_flavor_command_timeout: 300
```

## Configuration Schema

Each flavor in `neutron_router_flavors` requires:

```yaml
- name: <flavor_name>                    # Unique flavor name (e.g., "dynamic_vrf")
  description: <flavor_description>      # Human-readable description
  driver: <driver_class_path>            # Full Python path to driver class
  driver_description: <profile_desc>     # Service profile description
  service_profile_metainfo:              # JSON metadata for the profile
    vni_alloc: "off"|"on"|"auto"         # VNI allocation mode (see below)
    # ... other metadata as needed ...
  enabled: true|false                    # Whether flavor is enabled
```

### VNI Allocation Modes

The `vni_alloc` field in `service_profile_metainfo` controls VNI allocation:

- **`off`** (default): No VNI allocation; routers don't get a VXLAN VNI
  - Used by: `svi`, `cisco-asa`, `palo-alto`

- **`on`**: Admin-supplied only; admins must explicitly provide VNI
  - Used by: `static_vrf`

- **`auto`**: Auto-allocation; users don't specify VNI, it's allocated automatically
  - Used by: `dynamic_vrf`

## Dependencies

None - but requires OpenStack to be running and accessible via `openstack` CLI.

## Example Playbook

### In neutron-post-deploy.yaml

```yaml
---
- name: OpenStack Network
  hosts: neutron
  connection: local

  pre_tasks:
    - name: Check OpenStack connectivity
      ansible.builtin.import_tasks: tasks/check_openstack_auth.yml

  roles:
    - role: neutron_router_flavors
    - role: neutron_segment_range
    - role: openstack_subnet_pools
    - role: openstack_network
```

### With Custom Configuration

```yaml
---
- name: Configure Router Flavors
  hosts: localhost
  gather_facts: false
  roles:
    - role: neutron_router_flavors
      vars:
        openstack_cloud: my-cloud
        neutron_router_flavors:
          - name: custom_vrf
            description: "Custom VRF"
            driver: "my_company.routers.CustomVrf"
            driver_description: "Custom Stub"
            service_profile_metainfo:
              vni_alloc: "auto"
              custom_field: "custom_value"
            enabled: true
```

## Site-Config Integration

Add router flavor configuration to your site-config under the `neutron_router_flavors` key:

```yaml
---
# site/my-site/config.yaml
neutron_router_flavors:
  - name: dynamic_vrf
    description: "Fabric VRF with auto-allocated VNI"
    driver: "neutron_understack.l3_router.vrf.Vrf"
    driver_description: "VRF Stub"
    service_profile_metainfo:
      vni_alloc: "auto"
    enabled: true

  - name: static_vrf
    description: "Fabric VRF with static VNI"
    driver: "neutron_understack.l3_router.vrf.Vrf"
    driver_description: "VRF Stub"
    service_profile_metainfo:
      vni_alloc: "on"
    enabled: true

  - name: svi
    description: "Fabric SVI Gateway"
    driver: "neutron_understack.l3_router.svi.Svi"
    driver_description: "Defines SVI on Fabric"
    service_profile_metainfo:
      vni_alloc: "off"
    enabled: true

  - name: cisco-asa
    description: "Physical Cisco ASA"
    driver: "neutron_understack.l3_router.cisco_asa.CiscoAsa"
    driver_description: "ASA Stub"
    service_profile_metainfo:
      vni_alloc: "off"
    enabled: true

  - name: palo-alto
    description: "Physical Palo Alto"
    driver: "neutron_understack.l3_router.palo_alto.PaloAlto"
    driver_description: "PA Stub"
    service_profile_metainfo:
      vni_alloc: "off"
    enabled: true
```

## Task Breakdown

### main.yml
- Validates configuration
- Displays configured flavors
- Processes each flavor
- Verifies final state

### process_flavor.yml
For each router flavor, orchestrates:
1. Service profile creation/update
2. Flavor creation/update
3. Profile-to-flavor binding
4. Verification

### create_service_profile.yml
- Lists existing service profiles
- Searches for profile by driver (idempotent key)
- Creates if not found
- Updates metainfo if found
- Returns profile ID

### create_flavor.yml
- Checks if flavor exists by name (idempotent key)
- Creates if not found
- Updates description if found
- Returns flavor ID

### bind_profile_to_flavor.yml
- Gets current flavor details
- Checks if profile already bound (idempotent key)
- Removes old profiles if different
- Binds current profile if needed

### verify_flavor_binding.yml
- Verifies flavor exists
- Verifies profile is bound
- Verifies profile has correct driver
- Reports success or failure

### verify_flavors.yml
- Lists all configured router flavors
- Reports final state

## Idempotency

This role is fully idempotent:

- **Service profiles** are identified by **driver** (unique key)
- **Flavors** are identified by **name** (unique key)
- **Bindings** check existing relationships before acting
- **Running multiple times** produces the same result

Example:
```bash
# First run: creates everything
ansible-playbook neutron-post-deploy.yaml

# Second run: verifies everything is correct, makes no changes
ansible-playbook neutron-post-deploy.yaml

# Third run: same as second - idempotent!
ansible-playbook neutron-post-deploy.yaml
```

## Troubleshooting

### "No router flavors configured"

```
FAILED! - fatal for ...: No router flavors configured in neutron_router_flavors variable
```

**Solution**: Define `neutron_router_flavors` in your site-config or playbook.

### "Service profile list failed"

```
fatal: [localhost]: FAILED! - name: List existing service profiles
```

**Solution**:
- Verify OpenStack credentials: `export OS_CLOUD=<cloud_name>`
- Check clouds.yaml is accessible
- Verify Neutron API is reachable

### "Flavor binding failed"

```
fatal: [localhost]: FAILED! - name: Bind service profile to flavor
```

**Solution**:
- Check flavor exists: `openstack network flavor show <name>`
- Check profile exists: `openstack network flavor profile show <id>`
- Verify service profile is enabled
- Check Neutron service is running

### Debug Mode

Run with verbose output:

```bash
ansible-playbook neutron-post-deploy.yaml -v   # Verbose (moderate)
ansible-playbook neutron-post-deploy.yaml -vv  # Very verbose
ansible-playbook neutron-post-deploy.yaml -vvv # Debug (shows all details)
```

## Migration from Shell Script

### Before (network-flavors.sh)

```bash
#!/bin/sh
create_flavor() {
  name=$1
  desc=$2
  driver=$3
  driv_desc=$4
  # ... complex logic ...
}

create_flavor "dynamic_vrf" "..." "..." "..."
# ... repeated 5 times
```

**Problems:**
- Not idempotent (runs differently each time)
- Manual execution required
- No error recovery
- Hard to integrate with infrastructure-as-code

### After (neutron_router_flavors role)

```yaml
---
- role: neutron_router_flavors
```

**Benefits:**
- Fully idempotent
- Integrates with Ansible playbooks
- Automatic retries on failures
- Version controlled in git
- Consistent with other infrastructure

## Performance

Typical execution times:

- **First run** (creates everything): 10-15 seconds
- **Subsequent runs** (idempotent, verify only): 5-8 seconds

## Testing

### Test in Devstack

1. Deploy devstack environment
2. Source devstack credentials: `source /opt/stack/devstack/openrc admin`
3. Run role: `ansible-playbook test-flavors.yaml`

### Test Playbook

```yaml
---
- name: Test neutron_router_flavors role
  hosts: localhost
  gather_facts: false
  roles:
    - role: neutron_router_flavors
      vars:
        openstack_cloud: devstack
        neutron_router_flavors:
          - name: test-vrf
            description: "Test VRF"
            driver: "neutron_understack.l3_router.vrf.Vrf"
            driver_description: "VRF Stub"
            service_profile_metainfo:
              vni_alloc: "auto"
            enabled: true
```

### Verify Manually

```bash
# List all router flavors
openstack network flavor list --service-type L3_ROUTER_NAT

# Show flavor details
openstack network flavor show dynamic_vrf

# Show service profile
openstack network flavor profile show <profile-id>

# Show profile details with metainfo
openstack network flavor profile show <profile-id> -c metainfo
```

## License

Apache 2.0

## Author Information

UnderStack Team - https://github.com/rackerlabs/understack

## See Also

- [Neutron Networking Design Guide](../design-guide/neutron-networking.md)
- [Network Flavors Specification](https://specs.openstack.org/openstack/neutron-specs/specs/2023.2/ml2ovn-router-flavors.html)
- [OpenStack Neutron Documentation](https://docs.openstack.org/neutron/)
