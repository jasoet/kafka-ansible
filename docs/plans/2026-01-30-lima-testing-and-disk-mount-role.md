# Lima Testing Infrastructure & Disk Mount Role

## Overview

Replace Vultr (AMD64-only) with Lima for local ARM64 testing that matches production environment. Add disk mounting role to handle unformatted data disks.

## Problem

- Production uses ARM64 (aarch64) on AWS EC2
- Vultr only provides AMD64 machines
- Production servers have unformatted NVMe disks that need mounting
- No Ansible role exists for disk mounting

## Solution

### 1. Lima Test Infrastructure

Use Lima to create ARM64 Ubuntu 24.04 VMs on Apple Silicon Mac.

**VM Specifications:**

| Resource | Per VM | Notes |
|----------|--------|-------|
| CPU | 2 cores | Configurable |
| RAM | 4 GB | Configurable |
| Main disk | 20 GB | OS disk |
| Data disk | 10 GB | Unformatted (simulates production NVMe) |

**Lima Template (`tests/lima/kafka-node.yaml`):**

```yaml
minimumLimaVersion: "2.0.0"

images:
  - location: "https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-arm64.img"
    arch: "aarch64"

cpus: 2
memory: "4GiB"
disk: "20GiB"

additionalDisks:
  - name: "data"
    format: false  # Leaves disk raw like production

ssh:
  loadDotSSHPubKeys: true

containerd:
  system: false
  user: false
```

### 2. Python Cluster CLI

**Location:** `tests/lima/cluster.py`

**Commands:**

| Command | Description |
|---------|-------------|
| `create [--nodes N]` | Create N Kafka VMs (default: 1) |
| `destroy` | Delete all Kafka VMs |
| `inventory` | Generate Ansible inventory |
| `status` | Show cluster status |

**Usage:**

```bash
uv run tests/lima/cluster.py create           # Single node
uv run tests/lima/cluster.py create --nodes 3 # Full cluster
uv run tests/lima/cluster.py inventory
uv run tests/lima/cluster.py destroy
```

### 3. Disk Mount Role

**Location:** `roles/disk_mount/`

**Purpose:** Format and mount unformatted data disks idempotently.

**Variables (`defaults/main.yml`):**

```yaml
disk_mount_device: ""                    # Auto-detect if empty
disk_mount_path: "/data/kafka"
disk_mount_fstype: "xfs"
disk_mount_opts: "noatime,nodiratime"
disk_mount_owner: "kafka"
disk_mount_group: "kafka"
disk_mount_mode: "0750"
```

**Idempotent Behavior:**

| State | Action |
|-------|--------|
| Disk unformatted | Format with fstype |
| Disk already formatted | Skip format |
| Mount point missing | Create directory |
| Mount point exists | Skip creation |
| Fstab entry missing | Add entry |
| Fstab entry exists | Skip |
| Not mounted | Mount |
| Already mounted | Skip |

**Only fails on actual errors** (disk not found, permission denied, etc.)

### 4. Taskfile Integration

Update existing `.taskfiles/` structure:

**`.taskfiles/test-infra.yml`** (replace Terraform with Lima):

```yaml
version: '3'

vars:
  LIMA_DIR: ./tests/lima

tasks:
  up:
    desc: Create Lima test VMs
    dir: "{{.LIMA_DIR}}"
    cmds:
      - uv run cluster.py create {{.CLI_ARGS}}
      - uv run cluster.py inventory

  down:
    desc: Destroy Lima test VMs
    dir: "{{.LIMA_DIR}}"
    cmds:
      - uv run cluster.py destroy
      - rm -f ../../inventories/lima/hosts.yml

  status:
    desc: Show Lima VM status
    dir: "{{.LIMA_DIR}}"
    cmds:
      - uv run cluster.py status

  ssh:
    desc: "SSH into a test VM (usage: task test:infra:ssh -- kafka-1)"
    dir: "{{.LIMA_DIR}}"
    cmds:
      - limactl shell kafka-{{.CLI_ARGS | default "1"}}

  inventory:
    desc: Regenerate Ansible inventory
    dir: "{{.LIMA_DIR}}"
    cmds:
      - uv run cluster.py inventory
```

**`.taskfiles/test.yml`** (update for Lima):

```yaml
version: '3'

tasks:
  full:
    desc: Full test cycle (up → deploy → verify → down)
    cmds:
      - task: ":test:infra:up"
      - task: wait-for-ssh
      - task: ":ansible:deploy"
      - task: ":ansible:verify"
      - defer: { task: ":test:infra:down" }

  # ... wait-for-ssh updated for Lima inventory path
```

**`Taskfile.yml`** (update vars):

```yaml
vars:
  LIMA_DIR: ./tests/lima
  INVENTORY_LIMA: ./inventories/lima/hosts.yml
  INVENTORY_PROD: ./inventories/production/hosts.yml
```

## File Changes

### Create

- `tests/lima/kafka-node.yaml`
- `tests/lima/pyproject.toml`
- `tests/lima/cluster.py`
- `roles/disk_mount/defaults/main.yml`
- `roles/disk_mount/tasks/main.yml`
- `roles/disk_mount/handlers/main.yml`
- `roles/disk_mount/meta/main.yml`
- `inventories/lima/.gitkeep`

### Update

- `Taskfile.yml` - Update vars (remove TERRAFORM_DIR)
- `.taskfiles/test-infra.yml` - Replace Terraform with Lima
- `.taskfiles/test.yml` - Update for Lima paths
- `.taskfiles/ansible.yml` - Update default inventory to lima

### Delete

- `tests/terraform/` - Entire directory (no longer needed)
- `inventories/test/` - Replaced by `inventories/lima/`

## Testing Workflow

```bash
# Development (single node)
task lima:create
task lima:test
task lima:destroy

# Full cluster validation
uv run tests/lima/cluster.py create --nodes 3
task lima:test
task lima:destroy
```

## Production vs Local Comparison

| Aspect | Local (Lima) | Production (AWS) |
|--------|--------------|------------------|
| Architecture | aarch64 | aarch64 |
| OS | Ubuntu 24.04 | Ubuntu 24.04 |
| Data disk | /dev/vdb (unformatted) | /dev/nvme0n1 (unformatted) |
| Resources | 2 CPU, 4GB RAM | 8 CPU, 15GB RAM |
| Disk size | 10GB | 2TB |
