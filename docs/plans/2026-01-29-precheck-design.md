# Pre-flight Check Design for Kafka Production Deployment

## Overview

Create a pre-flight check playbook to validate AWS ARM (aarch64) production VMs before deploying Kafka. The precheck ensures VMs meet resource requirements, have proper network connectivity, and can download all required packages and binaries.

## Scope

### In Scope
- Pre-flight validation playbook (`playbooks/precheck.yml`)
- Taskfile task for production precheck
- Fix existing roles for ARM-only support

### Out of Scope
- x86/amd64 support (ARM-only deployment)
- Post-deployment verification (existing `verify.yml` handles this)

## Requirements

### Minimum VM Specifications
| Resource | Minimum |
|----------|---------|
| CPU | 8 vCPUs |
| Memory | 16 GB RAM |
| Disk | 2 TB available |
| OS | Ubuntu 24.04 LTS (Noble) |
| Architecture | aarch64 (ARM64) |

### Network Requirements
- Nodes must be able to reach each other via SSH/ping
- Local firewall (UFW) must allow ports 9092, 9093 (or be disabled)

### Download Requirements
- APT: `openjdk-21-jdk-headless`
- Kafka binary from Apache (ARM64)
- JMX Exporter JAR from Maven
- Kafka Exporter binary from GitHub (ARM64)

## Implementation

### 1. Role Fixes for ARM Support

#### `roles/java/defaults/main.yml`
Change `java_home` from amd64 to arm64:
```yaml
java_home: "/usr/lib/jvm/java-{{ java_version }}-openjdk-arm64"
```

#### `roles/kafka_exporter/defaults/main.yml`
Change download URL to ARM64 variant:
```yaml
kafka_exporter_download_url: "https://github.com/danielqsj/kafka_exporter/releases/download/v{{ kafka_exporter_version }}/kafka_exporter-{{ kafka_exporter_version }}.linux-arm64.tar.gz"
```

### 2. Pre-flight Playbook Structure

**File**: `playbooks/precheck.yml`

#### Play 1: Individual Node Checks (all kafka hosts)

| Check | Validation | Fail Condition |
|-------|------------|----------------|
| OS Version | `ansible_distribution_version == "24.04"` | Not Ubuntu 24.04 |
| Architecture | `ansible_architecture == "aarch64"` | Not ARM64 |
| CPU Cores | `ansible_processor_vcpus >= 8` | Less than 8 vCPUs |
| Memory | `ansible_memtotal_mb >= 15360` | Less than ~16GB |
| Disk Layout | Parse `/etc/fstab`, display all mounts | Informational |
| Disk Space | Check mount with 2TB+ available | No mount with 2TB+ |
| Firewall (UFW) | Check status and rules for 9092, 9093 | Ports blocked |
| APT Package | `apt-cache policy openjdk-21-jdk-headless` | Package not available |
| Kafka Download | HEAD request + download + `file` command | Not reachable or wrong arch |
| JMX Exporter | HEAD request to Maven URL | Not reachable |
| Kafka Exporter | HEAD request to GitHub ARM64 URL | Not reachable |

#### Play 2: Cluster Connectivity (from first node)

| Check | Validation | Fail Condition |
|-------|------------|----------------|
| SSH Reachability | Ansible delegate to each node | SSH fails |
| Ping Reachability | `ping -c 1` to each node | Ping fails |

#### Play 3: Summary Report

Display formatted summary of all checks per node.

### 3. Taskfile Integration

Add to `.taskfiles/ansible.yml`:
```yaml
precheck:prod:
  desc: Run pre-flight checks on production VMs
  vars:
    INVENTORY: ./inventories/production/hosts.yml
  cmds:
    - uv run ansible-playbook -i {{.INVENTORY}} playbooks/precheck.yml
  preconditions:
    - sh: "test -f {{.INVENTORY}}"
      msg: "Production inventory not found: {{.INVENTORY}}"
```

## Files Changed

| File | Action |
|------|--------|
| `playbooks/precheck.yml` | Create |
| `.taskfiles/ansible.yml` | Add `precheck:prod` task |
| `roles/java/defaults/main.yml` | Fix `java_home` for ARM |
| `roles/kafka_exporter/defaults/main.yml` | Fix download URL for ARM |

## Usage

```bash
# Run pre-flight checks on production
task ansible:precheck:prod

# Then deploy if checks pass
task ansible:deploy:prod
```

## Success Criteria

1. Precheck playbook fails fast with clear error messages when requirements not met
2. Precheck playbook shows summary report when all checks pass
3. Kafka deployment succeeds on ARM VMs after precheck passes
