# generate an SSH key
resource "tls_private_key" "ssh_key" {
  algorithm = "ED25519"
}

# save the private key to a local file
resource "local_file" "private_key" {
  content         = tls_private_key.ssh_key.private_key_openssh
  filename        = "${path.module}/id_ed25519"
  file_permission = "0600"
}

# save the public key to a local file
resource "local_file" "public_key" {
  content  = tls_private_key.ssh_key.public_key_openssh
  filename = "${path.module}/id_ed25519.pub"
}

resource "random_pet" "name" {
  keepers = {
    private_key_hash = sha256(tls_private_key.ssh_key.private_key_pem)
  }
  length = 1
}

resource "openstack_compute_keypair_v2" "ssh_keypair" {
  name       = random_pet.name.id
  public_key = tls_private_key.ssh_key.public_key_openssh
}

# Create the parent network and networks for the subports
resource "openstack_networking_network_v2" "parent_net" {
  name           = format("%s-parent", random_pet.name.id)
  admin_state_up = "true"
}

resource "openstack_networking_network_v2" "subport1_net" {
  name           = format("%s-subport1", random_pet.name.id)
  admin_state_up = "true"
  depends_on = [
    openstack_networking_network_v2.parent_net
  ]
}

resource "openstack_networking_network_v2" "subport2_net" {
  name           = format("%s-subport2", random_pet.name.id)
  admin_state_up = "true"
  depends_on = [
    openstack_networking_network_v2.subport1_net
  ]
}

# Create the subnets for parent and subports
resource "openstack_networking_subnet_v2" "parent_subnet" {
  name       = format("%s-subnet", openstack_networking_network_v2.parent_net.name)
  network_id = openstack_networking_network_v2.parent_net.id
  cidr       = var.network_subnet
  ip_version = 4
  # set default DNS servers
  dns_nameservers = ["8.8.8.8"]
  # not currently enabled for understack
  # enable_dhcp = false
  enable_dhcp = "false"
  depends_on = [
    openstack_networking_network_v2.parent_net
  ]
}

resource "openstack_networking_subnet_v2" "subport1_subnet" {
  name       = format("%s-subnet", openstack_networking_network_v2.subport1_net.name)
  network_id = openstack_networking_network_v2.subport1_net.id
  cidr       = var.network_subport1
  ip_version = 4
  enable_dhcp = "false"
  no_gateway = true
  depends_on = [
    openstack_networking_network_v2.subport1_net
  ]
}

resource "openstack_networking_subnet_v2" "subport2_subnet" {
  name       = format("%s-subnet", openstack_networking_network_v2.subport2_net.name)
  network_id = openstack_networking_network_v2.subport2_net.id
  cidr       = var.network_subport2
  ip_version = 4
  enable_dhcp = "false"
  no_gateway = true
  depends_on = [
    openstack_networking_network_v2.subport2_net
  ]
}

# Create the ports for the parent network and subports
resource "openstack_networking_port_v2" "parent_port" {
  name           = format("%s-port", openstack_networking_network_v2.parent_net.name)
  network_id     = openstack_networking_network_v2.parent_net.id
  # admin_state_up = "true"
  depends_on = [
    openstack_networking_subnet_v2.parent_subnet
  ]
}

resource "openstack_networking_port_v2" "subport1_port" {
  name           = format("%s-port", openstack_networking_network_v2.subport1_net.name)
  network_id     = openstack_networking_network_v2.subport1_net.id
  # admin_state_up = "true"
  depends_on = [
    openstack_networking_subnet_v2.subport1_subnet
  ]
}

resource "openstack_networking_port_v2" "subport2_port" {
  name           = format("%s-port", openstack_networking_network_v2.subport2_net.name)
  network_id     = openstack_networking_network_v2.subport2_net.id
  # admin_state_up = "true"
  depends_on = [
    openstack_networking_subnet_v2.subport2_subnet
  ]
}

# Create network trunk
resource "openstack_networking_trunk_v2" "network_trunk" {
  name           = format("%s-trunk", openstack_networking_network_v2.parent_net.name)
  admin_state_up = "true"
  port_id        = openstack_networking_port_v2.parent_port.id

  sub_port {
    port_id           = openstack_networking_port_v2.subport1_port.id
    segmentation_id   = var.network_segmentation_id1
    segmentation_type = "vlan"
  }
  sub_port {
    port_id           = openstack_networking_port_v2.subport2_port.id
    segmentation_id   = var.network_segmentation_id2
    segmentation_type = "vlan"
  }
}

# Create server with the trunk port
data "openstack_compute_flavor_v2" "test_flavor" {
  name = var.server_flavor
}

data "openstack_images_image_v2" "test_image" {
  name        = var.server_image
  most_recent = true
}

resource "openstack_compute_instance_v2" "tenant_server" {
  count     = var.server_count
  name      = format("%s-%02d", random_pet.name.id, count.index + 1)
  image_id  = data.openstack_images_image_v2.test_image.id
  flavor_id = data.openstack_compute_flavor_v2.test_flavor.id
  key_pair  = openstack_compute_keypair_v2.ssh_keypair.name
  config_drive = true

  network {
    port = openstack_networking_port_v2.parent_port.id
  }

  depends_on = [
    openstack_networking_trunk_v2.network_trunk,
    openstack_compute_keypair_v2.ssh_keypair
  ]
}
