# Using the Cloud

This section is for people **consuming** an UnderStack cloud: driving the
OpenStack APIs and CLI to get bare metal servers, images and networks. If you are
deploying or operating the cloud itself, you want
[Deploy](../deploy-guide/welcome.md) or
[Operations](../operator-guide/index.md) instead.

UnderStack is an OpenStack cloud, so upstream OpenStack documentation applies
directly. The pages here cover the parts that are specific to UnderStack —
mainly that the compute you get is a real machine rather than a virtual one.

## Set up your client

- [OpenStack CLI](openstack-cli.md) — installing the client, configuring
  `clouds.yaml` for single sign-on, and creating application credentials for
  Terraform and Ansible. **Start here**; the rest of this section assumes a
  working CLI.

## Working with servers

- [Operating System Images](openstack-image.md) — listing the available images,
  adding your own, and the image properties that matter for bare metal.
- [Graphical Console](openstack-console.md) — reaching a server's console when
  SSH is not an option, such as during boot or after a network change locked you
  out.
- [Server Firmware Updates](server-firmware-update.md) — requesting a firmware
  update on a server you hold, via node traits and runbooks.

## Automating

- [OpenStack Resource Controller (ORC)](openstack-resource-controller.md) —
  managing OpenStack resources as Kubernetes objects, if you would rather
  reconcile than script.

For Terraform, the
[OpenStack provider](https://registry.terraform.io/providers/terraform-provider-openstack/openstack/latest/docs)
works against UnderStack unchanged; `examples/` in the repository has working
configurations for multi-node builds, routers and trunk ports.

## Upstream documentation

Anything not specific to UnderStack is covered upstream:

- [OpenStack Client][osc] — the full command reference.
- [Bare Metal service (Ironic) user guide](https://docs.openstack.org/ironic/latest/user/index.html)
  — how bare metal provisioning differs from virtual machines.
- [Networking (Neutron) user guide](https://docs.openstack.org/neutron/latest/user/index.html)

[osc]: <https://docs.openstack.org/python-openstackclient/latest>
