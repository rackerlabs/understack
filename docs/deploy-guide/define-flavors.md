# Defining OpenStack Nova Flavors

Flavors are used to advertise to the user what hardware types are available
for consumption. Flavors must be defined and configured to map to Ironic
hardware types that are available.

## Flavor Definition with Crossplane

Create the following YAML to load.

```yaml
apiVersion: compute.openstack.crossplane.io/v1alpha1
kind: FlavorV2
metadata:
  name: gp1-small
spec:
  forProvider:
    name: gp1.small
    vcpus: 16
    ram: 98304
    disk: 480
    isPublic: true
    extraSpecs:
      'resources:CUSTOM_BAREMETAL_GP1SMALL': '1'
      'resources:DISK_GB': '0'
      'resources:MEMORY_MB': '0'
      'resources:VCPU': '0'
  providerConfigRef:
    name: provider-openstack-config
```
