provider "vultr" {
  api_key     = var.vultr_api_key
  rate_limit  = 100
  retry_limit = 3
}

# Get Ubuntu 24.04 LTS OS ID
data "vultr_os" "ubuntu" {
  filter {
    name   = "name"
    values = ["Ubuntu 24.04 LTS x64"]
  }
}

# Create Kafka test instances
resource "vultr_instance" "kafka" {
  count = var.instance_count

  label       = "${var.label_prefix}-${count.index + 1}"
  hostname    = "${var.label_prefix}-${count.index + 1}"
  region      = var.region
  plan        = var.plan
  os_id       = data.vultr_os.ubuntu.id
  ssh_key_ids = [var.ssh_key_id]

  tags = ["kafka", "test"]

  # Wait for instance to be ready
  backups          = "disabled"
  ddos_protection  = false
  activation_email = false
}
