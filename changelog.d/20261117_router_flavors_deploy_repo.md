### Deploy repo changes

Router-flavor definitions are now deployment-owned so sites can customize them through Kustomize. UnderStack no longer supplies the `dynamic-vrf`, `static-vrf`, `svi`, and `pa1410` `NeutronRouterFlavor` resources from `components/openstack-sync-plugins`.

Before upgrading UnderStack:

1. Update your deployment repository to supply the four CRs. In `undercloud-deploy`, they are shared under `hardware/neutron-router-flavors`; reference that directory from each site's `openstack-sync-plugins/kustomization.yaml`:

    ```yaml
    resources:
      - ../../hardware/neutron-router-flavors
      # Keep the site's existing resources here.
    ```

2. Keep the existing CR names, namespace, and specifications unchanged, including `spec.name`, credentials references, and service-profile metadata. Sync the deployment-repository changes before adopting the UnderStack removal. While both sources supply the same CRs, Argo CD may report a temporary `RepeatedResourceWarning`.

3. Upgrade UnderStack and resync the site's OpenStack sync plugins application. Confirm the four CRs remain present with their original UIDs and that the Neutron flavor and service-profile UUIDs and bindings are unchanged.

Do not upgrade UnderStack before the deployment repository supplies these CRs: Argo CD's automatic pruning can otherwise remove them.
