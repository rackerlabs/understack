# docker-bake.hcl
variable "REGISTRY" {
  default = "ghcr.io/rackerlabs/understack"
}

variable "TAG" {
  default = "latest"
}

variable "OPENSTACK_VERSION" {
  default = "2024.2"
}

# Default group for building all targets
group "default" {
  targets = [
    "ironic",
    "neutron",
    "keystone",
    "nova",
    "cinder",
    "octavia",
    "openstack-client",
    "dnsmasq",
    "ironic-nautobot-client",
    "nova-flavors",
    "ansible",
    "understack-tests"
  ]
}

# OpenStack services group
group "openstack" {
  targets = [
    "ironic",
    "neutron",
    "keystone",
    "nova",
    "cinder",
    "octavia",
    "openstack-client"
  ]
}

# Workflow containers group
group "workflows" {
  targets = [
    "ironic-nautobot-client",
    "nova-flavors",
    "ansible",
    "understack-tests"
  ]
}

# OpenStack service containers
target "ironic" {
  dockerfile = "containers/ironic/Dockerfile"
  context = "."
  tags = ["${REGISTRY}/ironic:${TAG}"]
  platforms = ["linux/amd64", "linux/arm64"]
  pull = true
  args = {
    OPENSTACK_VERSION = "${OPENSTACK_VERSION}"
  }
  labels = {
    "org.opencontainers.image.source" = "https://github.com/rackerlabs/understack"
    "org.opencontainers.image.description" = "UnderStack Ironic service"
    "org.opencontainers.image.version" = "${TAG}"
  }
}

target "neutron" {
  dockerfile = "containers/neutron/Dockerfile"
  context = "."
  tags = ["${REGISTRY}/neutron:${TAG}"]
  platforms = ["linux/amd64", "linux/arm64"]
  pull = true
  args = {
    OPENSTACK_VERSION = "${OPENSTACK_VERSION}"
  }
  labels = {
    "org.opencontainers.image.source" = "https://github.com/rackerlabs/understack"
    "org.opencontainers.image.description" = "UnderStack Neutron service"
    "org.opencontainers.image.version" = "${TAG}"
  }
}

target "keystone" {
  dockerfile = "containers/keystone/Dockerfile"
  context = "."
  tags = ["${REGISTRY}/keystone:${TAG}"]
  platforms = ["linux/amd64", "linux/arm64"]
  pull = true
  args = {
    OPENSTACK_VERSION = "${OPENSTACK_VERSION}"
  }
  labels = {
    "org.opencontainers.image.source" = "https://github.com/rackerlabs/understack"
    "org.opencontainers.image.description" = "UnderStack Keystone service"
    "org.opencontainers.image.version" = "${TAG}"
  }
}

target "nova" {
  dockerfile = "containers/nova/Dockerfile"
  context = "."
  tags = ["${REGISTRY}/nova:${TAG}"]
  platforms = ["linux/amd64", "linux/arm64"]
  pull = true
  args = {
    OPENSTACK_VERSION = "${OPENSTACK_VERSION}"
  }
  labels = {
    "org.opencontainers.image.source" = "https://github.com/rackerlabs/understack"
    "org.opencontainers.image.description" = "UnderStack Nova service"
    "org.opencontainers.image.version" = "${TAG}"
  }
}

target "cinder" {
  dockerfile = "containers/cinder/Dockerfile"
  context = "."
  tags = ["${REGISTRY}/cinder:${TAG}"]
  platforms = ["linux/amd64", "linux/arm64"]
  pull = true
  args = {
    OPENSTACK_VERSION = "${OPENSTACK_VERSION}"
  }
  labels = {
    "org.opencontainers.image.source" = "https://github.com/rackerlabs/understack"
    "org.opencontainers.image.description" = "UnderStack Cinder service"
    "org.opencontainers.image.version" = "${TAG}"
  }
}

target "octavia" {
  dockerfile = "containers/octavia/Dockerfile"
  context = "."
  tags = ["${REGISTRY}/octavia:${TAG}"]
  platforms = ["linux/amd64", "linux/arm64"]
  pull = true
  args = {
    OPENSTACK_VERSION = "${OPENSTACK_VERSION}"
  }
  labels = {
    "org.opencontainers.image.source" = "https://github.com/rackerlabs/understack"
    "org.opencontainers.image.description" = "UnderStack Octavia service"
    "org.opencontainers.image.version" = "${TAG}"
  }
}

target "openstack-client" {
  dockerfile = "containers/openstack-client/Dockerfile"
  context = "."
  tags = ["${REGISTRY}/openstack-client:${TAG}"]
  platforms = ["linux/amd64", "linux/arm64"]
  pull = true
  args = {
    OPENSTACK_VERSION = "${OPENSTACK_VERSION}"
  }
  labels = {
    "org.opencontainers.image.source" = "https://github.com/rackerlabs/understack"
    "org.opencontainers.image.description" = "UnderStack OpenStack client"
    "org.opencontainers.image.version" = "${TAG}"
  }
}

# Utility containers
target "dnsmasq" {
  dockerfile = "containers/dnsmasq/Dockerfile"
  context = "."
  tags = ["${REGISTRY}/dnsmasq:${TAG}"]
  platforms = ["linux/amd64", "linux/arm64"]
  pull = true
  labels = {
    "org.opencontainers.image.source" = "https://github.com/rackerlabs/understack"
    "org.opencontainers.image.description" = "UnderStack DNSmasq service"
    "org.opencontainers.image.version" = "${TAG}"
  }
}

# Workflow containers
target "ironic-nautobot-client" {
  dockerfile = "containers/ironic-nautobot-client/Dockerfile"
  context = "."
  tags = ["${REGISTRY}/ironic-nautobot-client:${TAG}"]
  platforms = ["linux/amd64", "linux/arm64"]
  pull = true
  target = "prod"
  labels = {
    "org.opencontainers.image.source" = "https://github.com/rackerlabs/understack"
    "org.opencontainers.image.description" = "UnderStack Ironic Nautobot client"
    "org.opencontainers.image.version" = "${TAG}"
  }
}

target "nova-flavors" {
  dockerfile = "containers/nova-flavors/Dockerfile"
  context = "."
  tags = ["${REGISTRY}/nova-flavors:${TAG}"]
  platforms = ["linux/amd64", "linux/arm64"]
  pull = true
  target = "prod"
  labels = {
    "org.opencontainers.image.source" = "https://github.com/rackerlabs/understack"
    "org.opencontainers.image.description" = "UnderStack Nova flavors manager"
    "org.opencontainers.image.version" = "${TAG}"
  }
}

target "ansible" {
  dockerfile = "containers/ansible/Dockerfile"
  context = "."
  tags = ["${REGISTRY}/ansible:${TAG}"]
  platforms = ["linux/amd64", "linux/arm64"]
  pull = true
  target = "prod"
  labels = {
    "org.opencontainers.image.source" = "https://github.com/rackerlabs/understack"
    "org.opencontainers.image.description" = "UnderStack Ansible runner"
    "org.opencontainers.image.version" = "${TAG}"
  }
}

target "understack-tests" {
  dockerfile = "containers/understack-tests/Dockerfile"
  context = "."
  tags = ["${REGISTRY}/understack-tests:${TAG}"]
  platforms = ["linux/amd64", "linux/arm64"]
  pull = true
  target = "prod"
  labels = {
    "org.opencontainers.image.source" = "https://github.com/rackerlabs/understack"
    "org.opencontainers.image.description" = "UnderStack test suite"
    "org.opencontainers.image.version" = "${TAG}"
  }
}
