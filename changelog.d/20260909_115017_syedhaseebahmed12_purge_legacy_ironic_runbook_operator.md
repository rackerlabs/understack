### Deprecations and removals

The legacy Ironic runbook operator, deprecated in v0.5.5, is now deleted:

- `components/ironic/runbook-crd/`
- `components/ironic/runbook-operator/`
- `containers/shell-operator-ironic/`

`shell-operator-ironic` is no longer built. Images already published to
`ghcr.io/rackerlabs/understack/shell-operator-ironic` are untouched, so a site
that has not finished migrating keeps a working image; it just stops receiving
new builds.

No action is required. Nothing rendered these files, so a resync sees no change.
Runbooks are reconciled by the `ironicRunbooks` hook in `openstack-sync-operator`
against the `IronicRunbook` CRD in
`components/openstack-sync-operator/crds/`, with reference CRs under
`components/openstack-sync-plugins/ironic-runbooks/examples/`.
