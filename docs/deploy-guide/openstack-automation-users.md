# OpenStack Automation Users

Should you need to an account in OpenStack for automation, you can do so
by creating a Kubernetes Secret in the `openstack` namespace with
the following metadata:

`understack.rackspace.com/keystone-user` (label):
  Defines the username in OpenStack Keystone in the `service` domain
  which will be created.

`understack.rackspace.com/keystone-role` (annotation):
  Defines what this account will have access to do. This is an annotation
  rather than a label so that it can hold a comma separated list of roles,
  which label values do not allow.

Possible roles are:

- `tenant-read` which allows read access to tenant resources
- `tenant-readwrite` which allows read and write access to tenant resources
- `tenant-admin` which has full admin access to tenant resources, including project creation
- `infra-read` which allows read access to infrastructure resources
- `infra-readwrite` which allows read and write access to infrastructure resources

Roles can be comma separated, for example `tenant-read,infra-read`.
Whitespace around the commas is ignored and unknown roles are logged and
skipped.

!!! note
    Reading the roles from a `understack.rackspace.com/keystone-role` label is
    deprecated but still supported when the annotation is absent. A single
    role can still be given that way, but new Secrets should use the
    annotation.

An example secret would look like:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mysvc
  annotations:
    understack.rackspace.com/keystone-role: tenant-read,infra-read
  labels:
    understack.rackspace.com/keystone-user: mysvc
type: Opaque
dataString:
  password: MY_PASSWORD
```
