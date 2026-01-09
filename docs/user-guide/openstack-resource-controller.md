# OpenStack Resource Controller (ORC)

UnderStack includes a deployment of [OpenStack Resource Controller (ORC)](https://k-orc.cloud/)
which lets users define OpenStack resources such as networks and servers as a YAML manifest.

Here's an example which creates a simple neutron network:

``` yaml
---
apiVersion: openstack.k-orc.cloud/v1alpha1
kind: Network
metadata:
  name: orc-test-network
spec:
  cloudCredentialsRef:
    cloudName: understack
    secretName: openstack-clouds
  managementPolicy: managed
  resource:
    description: My first ORC network
```

To use OpenStack Resource Controller, you will need to create a secret in the namespace
containing the OpenStack user's credentials: <https://k-orc.cloud/getting-started/#set-up-credentials>.

You can find a full example in <https://github.com/rackerlabs/understack/tree/main/examples/openstack-notifications>
