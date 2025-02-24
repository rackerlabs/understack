variable "server_count" {
  description = "How many servers to build"
  type        = number
  default     = 2
}

variable "server_image" {
  description = "The OS image to use for the servers"
  type        = string
  default     = "Ubuntu 24.04"
}

variable "server_flavor" {
  description = "Hardware flavor for the servers"
  type        = string
  default     = "gp2.small"
}

variable "network_subnet" {
  description = "Subnet to use for the network"
  type        = string
  default     = "192.168.0.0/24"
}

variable "external_network" {
  description = "External network for Gateway and Floating IP access"
  type        = string
  default     = "PUBLICNET"
}
