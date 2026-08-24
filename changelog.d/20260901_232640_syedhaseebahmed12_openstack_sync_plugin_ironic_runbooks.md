### Action required

Ironic runbooks are now reconciled by the `ironicRunbooks` hook in
`openstack-sync-operator`. The old `shell-operator-ironic` controller and its
runbook shell hooks have been removed.

Deploy the UnderStack ref that contains this hook and the deploy-repo changes
together. The hook must exist in the operator image before it is enabled.

### Deprecations and removals

- `components/ironic/runbook-operator/`
- `containers/shell-operator-ironic/`
- `components/ironic/runbook-crd/`

The `IronicRunbook` CRD now lives in
`components/openstack-sync-operator/crds/`. Example runbooks moved to
`components/openstack-sync-plugins/ironic-runbooks/examples/`.
