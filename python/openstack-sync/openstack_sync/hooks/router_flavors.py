#!/usr/bin/env python3
"""Shell-operator entrypoint for Neutron router flavor reconciliation."""

from __future__ import annotations

from openstack_sync.plugins.neutron.router_flavors.hook import main

if __name__ == "__main__":
    main()
