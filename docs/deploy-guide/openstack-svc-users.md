# OpenStack Service Users

Should you need to create service accounts in OpenStack you can do so
by creating a Kubernetes Secret in the `openstack` namespace with
the following labels:

`understack.rackspace.com/keystone-role`:
  Defines what this account will have access to do.

`understack.rackspace.com/keystone-user`:
  Defines the username in OpenStack Keystone in the `service` domain
  which will be created.

Possible roles are:

- `tenant-reader` which allows read access to tenant resources
- `tenant-readwrite` which allows read and write access to tenant resources
- `infra-reader` which allows read access to infrastructure resources
- `infra-readwrite` which allows read and write access to infrastructure resources

Roles can be comma separated.

An example secret would look like:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mysvc
  labels:
    understack.rackspace.com/keystone-role: tenant-reader
    understack.rackspace.com/keystone-user: mysvc
type: Opaque
dataString:
  password: MY_PASSWORD
```
