# openstack-sync-operator

Deploys the OpenStack sync shell-operator into the OpenStack namespace.

The operator chart owns the runtime pieces that must version with hook code: the
Deployment, ServiceAccount, RBAC, and CRDs under
`components/openstack-sync-operator/crds/`. Plugin custom resources live outside
the operator chart in the separate `openstack-sync-plugins` Application.

Enable the base operator with `site.openstack_sync_operator.enabled`. The base
operator can run with no plugin hooks enabled; in that state it starts only the
placeholder hook and its Role has no custom resource permissions.
