# Neutron

OpenStack Neutron is used for the user facing API for networks. While
much of the focus of Neutron is around virtual networks on top of
physical networks for delivering cloud services. However controlling
physical networks is supported and utilized by OpenStack Ironic for
example with the [networking-generic-switch][ngs] ML2 mechanism.

Given our focus on physical networks with physical switches, there
are some features we are disabling by default that can be enabled
in your specific deploy configs.

MTU override
:  Bare metal switch networks support using up to 9000 MTU. Neutron assumes
   a 50 byte overhead with the VXLAN type for encapsulation so we need to
   specify what the physical MTU is with the encapsulation overhead.
: `global_physnet_mtu = 9050`

Security Groups
: Our focus is on bare metal switches and not OpenFlow based OVS so these
  switches implement this differently or not at all. Disable this to not
  have confusiona until we can enable it generically.
: `extension_drivers` lacking `port_security`

[ngs]: <https://opendev.org/openstack/networking-generic-switch>
