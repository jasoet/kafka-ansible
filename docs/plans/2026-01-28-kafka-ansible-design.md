# Kafka Ansible Setup Design

## Overview

Ansible roles and playbook to deploy a production-ready Apache Kafka cluster using KRaft mode (no ZooKeeper).

## Requirements

| Requirement | Value |
|-------------|-------|
| Messages/sec | Up to 10K |
| Message size | Up to 2KB |
| Peak throughput | ~20MB/s |
| Consumer pattern | Batch processing, few times/day |
| Retention | 3 days |
| Storage per node | ~1TB starting point |

## Technology Choices

| Component | Decision | Rationale |
|-----------|----------|-----------|
| Kafka version | 4.1.1 | Latest stable, KRaft-only |
| Java version | OpenJDK 21 | Latest LTS, Kafka 4.x supported |
| Cluster topology | 3 nodes, combined mode | Broker + controller on each node |
| Target OS | Ubuntu 24.04 LTS | Fresh VM install |
| Security | PLAINTEXT | Internal trusted network |
| Installation | Binary tarball | Full version control |
| Python tooling | uv | Fast, clean dependency management |
| Testing | Molecule + Podman | Container-based role testing |

## Project Structure

```
kafka-ansible/
├── pyproject.toml
├── uv.lock
├── .python-version
├── ansible.cfg
├── roles/
│   ├── java/
│   ├── kafka/
│   ├── jmx_exporter/
│   └── kafka_exporter/
├── inventories/
│   ├── production/
│   │   ├── hosts.yml
│   │   └── group_vars/
│   │       └── kafka.yml
│   └── staging/
├── playbooks/
│   └── kafka.yml
└── docs/
    └── plans/
```

## Role Specifications

### 1. Java Role

Installs OpenJDK 21 headless from Ubuntu repositories.

**Variables:**
```yaml
java_version: "21"
java_package: "openjdk-{{ java_version }}-jdk-headless"
java_home: "/usr/lib/jvm/java-{{ java_version }}-openjdk-amd64"
```

**Tasks:**
1. Update apt cache
2. Install OpenJDK headless
3. Set JAVA_HOME in /etc/environment
4. Verify installation

### 2. Kafka Role

Installs and configures Kafka 4.1.1 in KRaft mode.

**Directory Layout:**
- Install: `/opt/kafka` (symlink to versioned dir)
- Data: `/data/kafka` (dedicated disk mount)
- Logs: `/var/log/kafka`
- Config: `/etc/kafka`
- User: `kafka:kafka`

**Variables:**
```yaml
# Version
kafka_version: "4.1.1"
kafka_scala_version: "2.13"
kafka_download_url: "https://downloads.apache.org/kafka/{{ kafka_version }}/kafka_{{ kafka_scala_version }}-{{ kafka_version }}.tgz"

# Directories
kafka_install_dir: "/opt/kafka"
kafka_data_dir: "/data/kafka"
kafka_log_dir: "/var/log/kafka"
kafka_config_dir: "/etc/kafka"

# User
kafka_user: "kafka"
kafka_group: "kafka"

# KRaft
kafka_cluster_id: ""                      # Generated once, shared across cluster
kafka_combined_mode: true

# Network
kafka_port: 9092
kafka_controller_port: 9093

# Retention (3 days)
kafka_log_retention_hours: 72
kafka_log_retention_bytes: 53687091200    # 50GB per partition

# Resource-aware tuning
kafka_heap_size: "{{ (ansible_memtotal_mb * 0.25) | int | max(1024) | min(8192) }}m"
kafka_num_network_threads: "{{ [(ansible_processor_vcpus / 2) | int, 3] | max }}"
kafka_num_io_threads: "{{ [(ansible_processor_vcpus * 2) | int, 8] | max }}"
kafka_num_partitions: 6

# Small message optimizations (2KB messages)
kafka_message_max_bytes: 1048576          # 1MB max
kafka_replica_fetch_max_bytes: 1048576
kafka_log_segment_bytes: 536870912        # 512MB segments

# Batch consumer friendly
kafka_fetch_min_bytes: 131072             # 128KB min fetch
kafka_fetch_max_wait_ms: 1000             # 1 second wait
```

**Tasks:**
1. Create kafka user/group
2. Create directories
3. Download and extract tarball
4. Symlink /opt/kafka to versioned directory
5. Generate server.properties from template
6. Generate cluster ID (once, on first node)
7. Format storage with kafka-storage.sh
8. Deploy systemd service unit
9. Enable and start service

**server.properties template (key settings):**
```properties
# KRaft mode
process.roles=broker,controller
node.id={{ kafka_node_id }}
controller.quorum.voters={{ kafka_quorum_voters }}
controller.listener.names=CONTROLLER

# Listeners
listeners=PLAINTEXT://:{{ kafka_port }},CONTROLLER://:{{ kafka_controller_port }}
advertised.listeners=PLAINTEXT://{{ ansible_fqdn }}:{{ kafka_port }}
inter.broker.listener.name=PLAINTEXT

# Directories
log.dirs={{ kafka_data_dir }}

# Retention
log.retention.hours={{ kafka_log_retention_hours }}
log.retention.bytes={{ kafka_log_retention_bytes }}

# Performance
num.network.threads={{ kafka_num_network_threads }}
num.io.threads={{ kafka_num_io_threads }}
num.partitions={{ kafka_num_partitions }}

# Small message tuning
message.max.bytes={{ kafka_message_max_bytes }}
replica.fetch.max.bytes={{ kafka_replica_fetch_max_bytes }}
log.segment.bytes={{ kafka_log_segment_bytes }}
fetch.min.bytes={{ kafka_fetch_min_bytes }}
fetch.max.wait.ms={{ kafka_fetch_max_wait_ms }}
```

**JVM settings (systemd unit):**
```
Environment="KAFKA_HEAP_OPTS=-Xms{{ kafka_heap_size }} -Xmx{{ kafka_heap_size }}"
Environment="KAFKA_JVM_PERFORMANCE_OPTS=-server -XX:+UseG1GC -XX:MaxGCPauseMillis=20 -XX:InitiatingHeapOccupancyPercent=35"
```

### 3. JMX Exporter Role

Runs as Java agent inside Kafka JVM. Exposes JVM and Kafka internal metrics.

**Variables:**
```yaml
jmx_exporter_version: "1.1.0"
jmx_exporter_port: 7071
jmx_exporter_install_dir: "/opt/jmx_exporter"
jmx_exporter_config_file: "/etc/kafka/jmx-exporter.yml"
jmx_exporter_download_url: "https://repo1.maven.org/maven2/io/prometheus/jmx/jmx_prometheus_javaagent/{{ jmx_exporter_version }}/jmx_prometheus_javaagent-{{ jmx_exporter_version }}.jar"
```

**Tasks:**
1. Create install directory
2. Download jmx_prometheus_javaagent jar
3. Deploy Kafka-specific metrics config
4. Update Kafka systemd unit with Java agent flag

**Kafka systemd addition:**
```
Environment="KAFKA_OPTS=-javaagent:{{ jmx_exporter_install_dir }}/jmx_prometheus_javaagent.jar={{ jmx_exporter_port }}:{{ jmx_exporter_config_file }}"
```

**Metrics endpoint:** `:7071/metrics`
- JVM heap, GC, threads
- Kafka broker metrics
- KRaft controller metrics

### 4. Kafka Exporter Role

Separate process connecting to Kafka API. Exposes consumer lag and topic metrics.

**Variables:**
```yaml
kafka_exporter_version: "1.8.0"
kafka_exporter_port: 9308
kafka_exporter_install_dir: "/opt/kafka_exporter"
kafka_exporter_user: "kafka"
kafka_exporter_download_url: "https://github.com/danielqsj/kafka_exporter/releases/download/v{{ kafka_exporter_version }}/kafka_exporter-{{ kafka_exporter_version }}.linux-amd64.tar.gz"
kafka_exporter_kafka_server: "localhost:9092"
kafka_exporter_extra_args: ""
```

**Tasks:**
1. Create install directory
2. Download and extract binary
3. Deploy systemd service unit
4. Enable and start service

**Metrics endpoint:** `:9308/metrics`
- Consumer group lag per partition
- Topic partition count, replicas, ISR
- Broker metadata

## Playbook

**playbooks/kafka.yml:**
```yaml
---
- name: Setup Kafka Cluster
  hosts: kafka
  become: true

  pre_tasks:
    - name: Gather facts
      ansible.builtin.setup:
        gather_subset:
          - hardware
          - network

  roles:
    - role: java
      tags: [java]

    - role: kafka
      tags: [kafka]

    - role: jmx_exporter
      tags: [jmx, monitoring]

    - role: kafka_exporter
      tags: [kafka_exporter, monitoring]
```

## Inventory

**inventories/production/hosts.yml:**
```yaml
all:
  children:
    kafka:
      hosts:
        kafka-1.internal:
          kafka_node_id: 1
        kafka-2.internal:
          kafka_node_id: 2
        kafka-3.internal:
          kafka_node_id: 3
      vars:
        kafka_quorum_voters: "1@kafka-1.internal:9093,2@kafka-2.internal:9093,3@kafka-3.internal:9093"
```

**inventories/production/group_vars/kafka.yml:**
```yaml
kafka_heap_size: "6g"
kafka_log_retention_hours: 72
kafka_log_retention_bytes: 53687091200
kafka_data_dir: "/data/kafka"
```

## Python Environment (uv)

**pyproject.toml:**
```toml
[project]
name = "kafka-ansible"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    "ansible-core>=2.16",
    "ansible-lint>=6.0",
    "molecule>=6.0",
    "molecule-podman>=2.0",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
]
```

**.python-version:**
```
3.13
```

**Usage:**
```bash
# Setup
uv sync

# Run playbook
uv run ansible-playbook playbooks/kafka.yml -i inventories/production/hosts.yml

# Lint
uv run ansible-lint

# Test role
uv run molecule test -s default
```

## Testing with Molecule

**roles/kafka/molecule/default/molecule.yml:**
```yaml
dependency:
  name: galaxy

driver:
  name: podman

platforms:
  - name: kafka-1
    image: ubuntu:24.04
    privileged: true
    command: /sbin/init
    systemd: true
    groups:
      - kafka
  - name: kafka-2
    image: ubuntu:24.04
    privileged: true
    command: /sbin/init
    systemd: true
    groups:
      - kafka
  - name: kafka-3
    image: ubuntu:24.04
    privileged: true
    command: /sbin/init
    systemd: true
    groups:
      - kafka

provisioner:
  name: ansible
  inventory:
    group_vars:
      kafka:
        kafka_quorum_voters: "1@kafka-1:9093,2@kafka-2:9093,3@kafka-3:9093"
    host_vars:
      kafka-1:
        kafka_node_id: 1
      kafka-2:
        kafka_node_id: 2
      kafka-3:
        kafka_node_id: 3

verifier:
  name: ansible
```

**Verification tasks:**
- Kafka service running
- Port 9092 listening
- Port 7071 (JMX) listening
- Port 9308 (Kafka exporter) listening

## VM Sizing Guide

| Profile | vCPU | RAM | Disk | Capacity |
|---------|------|-----|------|----------|
| Starting | 4 | 8GB | 1TB | ~3K msg/s |
| Recommended | 8 | 16GB | 1TB | ~7K msg/s |
| Full capacity | 16 | 32GB | 2TB | 10K+ msg/s |

Resource-aware variables auto-adjust as VMs are resized.

## Storage Estimates

With 3-day retention at varying load:

| Sustained rate | Daily volume | 3-day retention | Per node (3 replicas) |
|----------------|--------------|-----------------|----------------------|
| 2K msg/s (20%) | ~350GB | ~1TB | ~350GB |
| 5K msg/s (50%) | ~850GB | ~2.5TB | ~850GB |
| 10K msg/s (100%) | ~1.7TB | ~5TB | ~1.7TB |

Starting with 1TB per node covers realistic early usage with room to grow.

## Metrics Endpoints Summary

| Exporter | Port | Metrics |
|----------|------|---------|
| JMX Exporter | 7071 | JVM heap, GC, threads, Kafka internals |
| Kafka Exporter | 9308 | Consumer lag, topic/partition stats |

Configure Prometheus to scrape both endpoints from each Kafka node.
