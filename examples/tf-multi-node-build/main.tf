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

resource "openstack_networking_network_v2" "tenant_net" {
  name           = random_pet.name.id
  admin_state_up = "true"
}

resource "openstack_networking_subnet_v2" "tenant_subnet" {
  name       = random_pet.name.id
  network_id = openstack_networking_network_v2.tenant_net.id
  cidr       = var.network_subnet
  ip_version = 4
  # set default DNS servers
  dns_nameservers = ["8.8.8.8"]
  # not currently enabled for understack
  enable_dhcp = false
}

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

  network {
    uuid = openstack_networking_network_v2.tenant_net.id
  }

  depends_on = [
    openstack_networking_subnet_v2.tenant_subnet,
    openstack_networking_network_v2.tenant_net,
    openstack_compute_keypair_v2.ssh_keypair
  ]
}
