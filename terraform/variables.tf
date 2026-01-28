variable "vultr_api_key" {
  description = "Vultr API key"
  type        = string
  sensitive   = true
}

variable "ssh_key_id" {
  description = "Vultr SSH key ID"
  type        = string
  default     = "ed68e543-2daa-4539-82a8-847d2866b006"
}

variable "region" {
  description = "Vultr region"
  type        = string
  default     = "nrt"
}

variable "plan" {
  description = "Vultr VM plan"
  type        = string
  default     = "vc2-1c-1gb"
}

variable "os_id" {
  description = "Vultr OS ID for Ubuntu 24.04 LTS"
  type        = number
  default     = 2284
}

variable "instance_count" {
  description = "Number of Kafka nodes"
  type        = number
  default     = 3
}

variable "label_prefix" {
  description = "Prefix for instance labels"
  type        = string
  default     = "kafka-test"
}
