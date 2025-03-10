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
  description = "Subnet to use for the first network"
  type        = string
  default     = "192.168.0.0/24"
}

variable "network_subport1" {
  description = "Subnet to use for the second network"
  type        = string
  default     = "192.168.1.0/24"
}

variable "network_subport2" {
  description = "Subnet to use for the third network"
  type        = string
  default     = "192.168.2.0/24"
}

variable "network_segmentation_id1" {
  description = "Segmentation ID for network_subport1"
  type        = string
  default     = "1000"
}

variable "network_segmentation_id2" {
  description = "Segmentation ID for network_subport2"
  type        = string
  default     = "2000"
}
