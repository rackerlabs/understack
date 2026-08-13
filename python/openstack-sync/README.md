# openstack-sync

Shell-operator package for OpenStack reconciliation hooks.

The operator image ships with a no-op placeholder hook and resource-specific
sync hooks under `openstack_sync/hooks/`. The Neutron router flavor hook is
implemented under `openstack_sync/plugins/neutron/router_flavors/` and exposed
to shell-operator as `/hooks/router_flavors.py`.
