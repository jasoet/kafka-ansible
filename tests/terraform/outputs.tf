output "instance_ips" {
  description = "IP addresses of Kafka instances"
  value = {
    for instance in vultr_instance.kafka :
    instance.hostname => instance.main_ip
  }
}

output "quorum_voters" {
  description = "Kafka quorum voters string"
  value = join(",", [
    for idx, instance in vultr_instance.kafka :
    "${idx + 1}@${instance.main_ip}:9093"
  ])
}

# Generate inventory file
resource "local_file" "inventory" {
  content = templatefile("${path.module}/templates/inventory.tpl", {
    instances     = vultr_instance.kafka
    quorum_voters = join(",", [
      for idx, instance in vultr_instance.kafka :
      "${idx + 1}@${instance.main_ip}:9093"
    ])
  })
  filename        = "${path.module}/../../inventories/test/hosts.yml"
  file_permission = "0644"
}

output "inventory_path" {
  description = "Path to generated inventory file"
  value       = local_file.inventory.filename
}
