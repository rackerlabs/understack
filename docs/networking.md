# Networking

!!! warning Networking Configuration
    Your networking configurations in UnderStack are highly dependent on
    your own environment.

## MetalLB Load Balancer for DHCP

We are using [MetalLB](https://metallb.io/) to provide a TCP/UDP load balancer
for dnsmasq's DHCP server.

The MetalLB configuration you will use depends on the network and physical
server interface in your environment.

Here's an example MetalLB manifest where we use `192.168.200.2` as our DHCP
load balancer IP address, and on our server running UnderStack services, we
will use ethernet interface `eno2`.

```yaml
---
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: lb-provisioning
  namespace: metallb-system
spec:
  addresses:
  - 192.168.200.2/32  # IMPORTANT: this is the load balancer IP we will use for DHCP
  autoAssign: true
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: lb-provisioning-advertisement
  namespace: metallb-system
spec:
  ipAddressPools:
  - lb-provisioning
  interfaces:
  - eno2  # IMPORTANT: this is the physical interface on your understack server
```

## DHCP Dnsmasq Configuration

You will want to review and edit the dnsmasq DHCP configuration for your environment:
<https://github.com/rackerlabs/understack/blob/main/components/ironic/dnsmasq-cm.yaml>

The important settings to review are `DHCP_RANGE`, `DHCP_RANGE_ROUTER`, and `INGRESS_IP`.
