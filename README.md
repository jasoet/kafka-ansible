# Kafka Ansible

Ansible roles and playbook to deploy a production-ready Apache Kafka cluster using KRaft mode.

## Features

- **Kafka 4.1.1** with KRaft consensus (no ZooKeeper)
- **3-node cluster** in combined mode (broker + controller)
- **Resource-aware tuning** - auto-scales with VM specs
- **Monitoring ready** - JMX and Kafka exporters for Prometheus

## Requirements

- Ubuntu 24.04 LTS target hosts
- Python 3.11+ with uv
- Terraform (for testing with Vultr VMs)
- SSH access to target hosts

## Quick Start

```bash
# Install dependencies
uv sync

# Edit inventory with your hosts
vim inventories/production/hosts.yml

# Run playbook
uv run ansible-playbook playbooks/kafka.yml -i inventories/production/hosts.yml
```

## Inventory Example

```yaml
all:
  children:
    kafka:
      hosts:
        kafka-1.example.com:
          kafka_node_id: 1
        kafka-2.example.com:
          kafka_node_id: 2
        kafka-3.example.com:
          kafka_node_id: 3
      vars:
        kafka_quorum_voters: "1@kafka-1.example.com:9093,2@kafka-2.example.com:9093,3@kafka-3.example.com:9093"
```

## Roles

| Role | Description | Port |
|------|-------------|------|
| java | OpenJDK 21 installation | - |
| kafka | Kafka 4.1.1 KRaft cluster | 9092, 9093 |
| jmx_exporter | JVM/Kafka metrics | 7071 |
| kafka_exporter | Consumer lag metrics | 9308 |

## Configuration

Key variables (set in `inventories/<env>/group_vars/kafka.yml`):

```yaml
# Retention
kafka_log_retention_hours: 72        # 3 days
kafka_log_retention_bytes: 53687091200  # 50GB per partition

# Performance (auto-calculated if not set)
kafka_heap_size: "6g"
kafka_num_partitions: 6
```

See `roles/kafka/defaults/main.yml` for all options.

## VM Sizing

| Profile | vCPU | RAM | Disk | Capacity |
|---------|------|-----|------|----------|
| Starting | 4 | 8GB | 1TB | ~3K msg/s |
| Recommended | 8 | 16GB | 1TB | ~7K msg/s |
| Full | 16 | 32GB | 2TB | 10K+ msg/s |

## License

MIT
