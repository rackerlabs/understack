# OpenStack Automation Users

Should you need to an account in OpenStack for automation, you can do so
by creating a Kubernetes Secret in the `openstack` namespace with
the following metadata:

`keystone.understack.rackspace.com/account` (label):
  Triggers the creation of the account. Only its presence is checked, not
  its value, so set it to `"true"`.

`understack.rackspace.com/keystone-user` (label):
  Defines the username in OpenStack Keystone which will be created. When
  absent, the name of the Secret is used.

`understack.rackspace.com/keystone-roles` (annotation):
  Defines what this account will have access to do. This is an annotation
  rather than a label so that it can hold a comma separated list of roles,
  which label values do not allow.

Possible roles are:

- `tenant-read` which allows read access to tenant resources
- `tenant-readwrite` which allows read and write access to tenant resources
- `tenant-admin` which has full admin access to tenant resources, including project creation
- `infra-read` which allows read access to infrastructure resources
- `infra-readwrite` which allows read and write access to infrastructure resources

A role can also be written as `DOMAIN.ROLE`, which grants the Keystone role
`ROLE` on the Keystone domain `DOMAIN`, inherited by every project in that
domain. Both forms can be mixed in one list.

If any entry uses the `DOMAIN.ROLE` form, the account is created in the
`machine` Keystone domain, and that domain must already exist. Otherwise it is
created in the `service` domain. Changing which form a Secret uses therefore
creates a new account in the other domain rather than moving the old one, and
the credentials' `user_domain_name` must be updated to match.

Roles can be comma separated, for example `tenant-read,infra-read`.
Whitespace around the commas is ignored and unknown roles are logged and
skipped.

!!! note
    Reading the roles from a `understack.rackspace.com/keystone-role` label is
    deprecated but still supported when the annotation is absent. The Secret
    still needs the `keystone.understack.rackspace.com/account` label. A single
    role can still be given that way, but new Secrets should use the
    annotation.

An example secret would look like:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mysvc
  annotations:
    understack.rackspace.com/keystone-roles: tenant-read,infra-read
  labels:
    keystone.understack.rackspace.com/account: "true"
    understack.rackspace.com/keystone-user: mysvc
type: Opaque
dataString:
  password: MY_PASSWORD
```
