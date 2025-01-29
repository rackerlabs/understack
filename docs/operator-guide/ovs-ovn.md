# OVN / Open vSwitch

## Debugging OVN / Open vSwitch

To troubleshoot OVN specific issues you'll want to refer to
the [OVN manual pages](https://docs.ovn.org/en/latest/ref/index.html).

To troubleshoot OVS specific issues you'll want to refer to
the [OVS manual pages](https://docs.openvswitch.org/en/latest/ref/#man-pages).

The `ovn-` prefixed commands can be run from the `ovn-` prefixed pods.
Specifically the north and south DB pods will have the most best data.

The `ovs-` prefixed commands should be run from the `openvswitch` pods.
