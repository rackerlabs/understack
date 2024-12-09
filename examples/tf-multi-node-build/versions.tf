terraform {
  required_providers {
    local = {
      source = "hashicorp/local"
    }
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 2.1.0"
    }
    random = {
      source = "hashicorp/random"
    }
  }
}
