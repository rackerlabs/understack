### Notes

OpenStack sync CR deletions now wait for the operator to finish delete cleanup
before Kubernetes garbage-collects the CR. The openstack-sync-operator chart now
grants hooks `patch` on the main custom resource so they can add and remove the
framework finalizer. During deletion, a CR may remain in `Terminating` until the
matching OpenStack prune operation succeeds.
