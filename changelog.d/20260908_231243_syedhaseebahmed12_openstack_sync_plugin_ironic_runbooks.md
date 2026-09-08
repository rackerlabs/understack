### Action required

Ironic runbooks are now reconciled by the `ironicRunbooks` hook in
`openstack-sync-operator`, and the `IronicRunbook` CRD moved to a new API group.
Existing runbook CRs are not migrated for you: they are deleted, and you
re-apply them in the new shape.

`ironicrunbooks.baremetal.ironicproject.org` is no longer rendered by
`components/ironic`, so ArgoCD prunes it. Deleting a CRD cascade-deletes every
custom resource stored under it, so all existing `IronicRunbook` objects go with
it. The runbooks themselves stay in Ironic, but nothing reconciles them until a
new-group CR adopts them by name.

1. Re-author every runbook CR under the new group. Three fields change:

    ```yaml
    # before
    apiVersion: baremetal.ironicproject.org/v1alpha1
    kind: IronicRunbook
    spec:
      runbookName: CUSTOM_FIRMWARE_UPDATE_R740XD

    # after
    apiVersion: ironic.understack.rackspace.net/v1alpha1
    kind: IronicRunbook
    spec:
      cloudCredentialsRef:        # new, required
        secretName: infrasetup-system
        cloudName: understack
      runbookName: CUSTOM_FIRMWARE_UPDATE_R740XD
      traits:                     # new, required, at least one
        - CUSTOM_FIRMWARE_UPDATE_R740XD
    ```

    `spec.traits` is required because Ironic API microversion 1.112 changed how
    a runbook is matched to a node. Before 1.112 the runbook *name* had to equal
    a node trait; from 1.112 the node must carry one of the runbook's `traits`,
    and Ironic rejects a clean or service request naming a runbook that has
    none. A CR that omits `traits` is now rejected on apply.

    Keep `spec.runbookName` equal to the trait if a workflow resolves the
    runbook by trait name. `server-firmware-update` does exactly that, so
    renaming those runbooks would stop it finding them.

2. Move the CRs in your deploy repo from `<site>/ironic/` to
   `<site>/openstack-sync-plugins/`, and remove the reference from
   `<site>/ironic/kustomization.yaml`. Do both. If the CRs are still listed by
   the ironic Application while also listed by the openstack-sync-plugins
   Application, two Applications claim the same objects and both run with
   `prune: true`.

3. Enable the hook for the site, once it is pinned to an operator image that
   contains `/hooks/ironic_runbooks.py`:

    ```yaml title="<deploy-repo>/<site>/openstack-sync-operator/values.yaml"
    plugins:
      ironicRunbooks: true
    ```

    Deploy the UnderStack ref containing the hook and the deploy repo changes
    together. The hook must exist in the operator image before it is enabled.

4. Confirm Ironic serves API microversion 1.112 or later. The hook refuses to
   run against an older Ironic rather than syncing partial state.

The `bmc-maintenance` runbook is no longer deployed for you. It used to be
applied to every site from `components/ironic/runbook-crd/`, and it is now only
a reference CR at
`components/openstack-sync-plugins/ironic-runbooks/examples/bmc_maintenance.yaml`,
which nothing applies. Sites that want it own it now.

The runbook already in Ironic is not deleted. It carries none of the operator's
ownership markers, so pruning would skip it even with `PRUNE` enabled, and
`openstack baremetal node clean --runbook bmc-maintenance` keeps working on
nodes carrying `CUSTOM_DELL_IDRAC`. What you lose is reconciliation: no CR
describes it, so drift is no longer corrected and edits are no longer reverted.

If you want it managed again, copy the example into
`<deploy-repo>/<site>/openstack-sync-plugins/` and add it to that directory's
`kustomization.yaml`. Two things differ from the version that used to be
deployed. It needs `spec.cloudCredentialsRef`, and the secret must be
system-scoped, because Ironic will not let a project-scoped token publish a
public runbook. And the example sets `public: true`, which the deployed version
did not: a runbook that is neither public nor owned is invisible to every
project, so the old one could not actually be seen by the projects meant to use
it.

Sequencing caution: the legacy `shell-operator-ironic` deployment is removed in
the same change that stops rendering the old CRD, and ArgoCD gives no ordering
guarantee between the two. If the old CRD is pruned while that pod is still
running, its delete hook fires for each cascade-deleted CR and removes those
runbooks from Ironic. Scale `shell-operator-ironic` to zero before syncing if
you need to avoid that window.

### Deploy repo changes

Per-site runbook CRs move from `<site>/ironic/` to
`<site>/openstack-sync-plugins/`, listed by that directory's
`kustomization.yaml`. Pruning is off by default, so a removed CR leaves its
runbook in Ironic. To have the hook delete it, enable pruning before removing
the CR:

```yaml title="<deploy-repo>/<site>/openstack-sync-operator/values.yaml"
pluginData:
  ironicRunbooks:
    hook:
      env:
        PRUNE: "true"
```

Pruning only ever deletes runbooks the operator owns, meaning those carrying its
`_understack_runbook_*` markers in `extra`. Anything else is left in place.

### Deprecations and removals

These are no longer rendered by any kustomization, and the container is no
longer deployed:

- `components/ironic/runbook-crd/`
- `components/ironic/runbook-operator/`
- `containers/shell-operator-ironic/`

They are left on disk for one release so a site mid-migration can still read the
old manifests, and are deleted in a follow-up cleanup change after the next
release. Do not add new references to them.
