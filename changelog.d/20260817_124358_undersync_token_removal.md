### Deprecations and removals

The `undersync-switch` workflow now authenticates to Undersync with the
OpenStack credentials in the `baremetal-manage` Secret instead of a static
bearer token, matching how the Neutron mechanism driver already calls Undersync.
Nothing in UnderStack reads the `undersync-token` Secret any more, so you can
remove it from your deploy repo.

The workflow also no longer mounts `nautobot-token`, which it never used.
