# Lima Testing Infrastructure & Disk Mount Role - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Vultr/Terraform with Lima for local ARM64 testing and create disk mounting role.

**Architecture:** Python CLI manages Lima VMs with unformatted data disks. Ansible role handles idempotent disk formatting/mounting. Taskfiles updated to use new infrastructure.

**Tech Stack:** Lima, Python 3.11+, uv, Ansible 2.16+, xfsprogs

---

## Task 1: Delete Terraform Infrastructure

**Files:**
- Delete: `tests/terraform/` (entire directory)
- Delete: `inventories/test/` (entire directory)

**Step 1: Remove Terraform directory**

```bash
rm -rf tests/terraform
```

**Step 2: Remove test inventory directory**

```bash
rm -rf inventories/test
```

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove Vultr/Terraform test infrastructure"
```

---

## Task 2: Create Lima Directory Structure

**Files:**
- Create: `tests/lima/` directory
- Create: `inventories/lima/.gitkeep`

**Step 1: Create directories**

```bash
mkdir -p tests/lima
mkdir -p inventories/lima
touch inventories/lima/.gitkeep
```

**Step 2: Commit**

```bash
git add tests/lima inventories/lima
git commit -m "chore: add Lima test infrastructure directories"
```

---

## Task 3: Create Lima Template

**Files:**
- Create: `tests/lima/kafka-node.yaml`

**Step 1: Create Lima VM template**

```yaml
# Lima VM template for Kafka testing
# Matches production: Ubuntu 24.04 ARM64 with unformatted data disk

minimumLimaVersion: "2.0.0"

images:
  - location: "https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-arm64.img"
    arch: "aarch64"

cpus: 2
memory: "4GiB"
disk: "20GiB"

# Additional unformatted disk - simulates production NVMe
additionalDisks:
  - name: "data"
    format: false

ssh:
  loadDotSSHPubKeys: true

# Disable container runtimes - not needed for Ansible testing
containerd:
  system: false
  user: false
```

**Step 2: Commit**

```bash
git add tests/lima/kafka-node.yaml
git commit -m "feat(lima): add VM template with unformatted data disk"
```

---

## Task 4: Create Python Project Configuration

**Files:**
- Create: `tests/lima/pyproject.toml`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "kafka-lima-cluster"
version = "0.1.0"
description = "Lima cluster management for Kafka Ansible testing"
requires-python = ">=3.11"
dependencies = [
    "pyyaml>=6.0",
]

[project.scripts]
cluster = "cluster:main"
```

**Step 2: Commit**

```bash
git add tests/lima/pyproject.toml
git commit -m "feat(lima): add Python project configuration"
```

---

## Task 5: Create Python Cluster CLI

**Files:**
- Create: `tests/lima/cluster.py`

**Step 1: Create cluster.py**

```python
#!/usr/bin/env python3
"""Lima Kafka cluster management CLI."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent / "kafka-node.yaml"
INVENTORY_PATH = Path(__file__).parent.parent.parent / "inventories" / "lima" / "hosts.yml"
VM_PREFIX = "kafka"


def run_cmd(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def get_vm_list() -> list[dict]:
    """Get list of Kafka VMs from Lima."""
    result = run_cmd(["limactl", "list", "--json"], capture=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return []

    vms = []
    for line in result.stdout.strip().split("\n"):
        if line:
            vm = json.loads(line)
            if vm.get("name", "").startswith(VM_PREFIX):
                vms.append(vm)
    return vms


def create(nodes: int = 1) -> None:
    """Create Kafka test VMs."""
    print(f"Creating {nodes} Kafka VM(s)...")

    for i in range(1, nodes + 1):
        name = f"{VM_PREFIX}-{i}"
        print(f"\n--- Creating {name} ---")

        # Check if VM already exists
        existing = get_vm_list()
        if any(vm["name"] == name for vm in existing):
            print(f"{name} already exists, skipping...")
            continue

        # Create VM
        run_cmd([
            "limactl", "create",
            "--name", name,
            "--tty=false",
            str(TEMPLATE_PATH)
        ])

        # Start VM
        print(f"Starting {name}...")
        run_cmd(["limactl", "start", name])

    print("\n--- All VMs created ---")
    status()


def destroy() -> None:
    """Destroy all Kafka test VMs."""
    vms = get_vm_list()

    if not vms:
        print("No Kafka VMs found.")
        return

    print(f"Destroying {len(vms)} VM(s)...")

    for vm in vms:
        name = vm["name"]
        print(f"Deleting {name}...")
        run_cmd(["limactl", "delete", "--force", name], check=False)

    # Remove inventory file
    if INVENTORY_PATH.exists():
        INVENTORY_PATH.unlink()
        print(f"Removed {INVENTORY_PATH}")

    print("All Kafka VMs destroyed.")


def status() -> None:
    """Show status of Kafka VMs."""
    vms = get_vm_list()

    if not vms:
        print("No Kafka VMs found.")
        return

    print(f"\n{'Name':<12} {'Status':<10} {'SSH':<25} {'Arch':<10}")
    print("-" * 60)

    for vm in vms:
        name = vm.get("name", "unknown")
        vm_status = vm.get("status", "unknown")
        arch = vm.get("arch", "unknown")

        # Get SSH info
        ssh_address = "-"
        if vm_status == "Running":
            ssh_info = vm.get("sshLocalPort")
            if ssh_info:
                ssh_address = f"127.0.0.1:{ssh_info}"

        print(f"{name:<12} {vm_status:<10} {ssh_address:<25} {arch:<10}")


def inventory() -> None:
    """Generate Ansible inventory from running VMs."""
    vms = get_vm_list()
    running_vms = [vm for vm in vms if vm.get("status") == "Running"]

    if not running_vms:
        print("No running Kafka VMs found. Start VMs first.")
        sys.exit(1)

    # Get current user for SSH
    import getpass
    user = getpass.getuser()

    # Build inventory
    hosts = {}
    quorum_voters = []

    for i, vm in enumerate(sorted(running_vms, key=lambda x: x["name"]), start=1):
        name = vm["name"]
        port = vm.get("sshLocalPort")

        if not port:
            print(f"Warning: {name} has no SSH port, skipping...")
            continue

        hosts[name] = {
            "ansible_host": "127.0.0.1",
            "ansible_port": port,
            "ansible_user": user,
            "kafka_node_id": i,
        }

        # For quorum voters, use the VM name as hostname (resolved inside VM)
        quorum_voters.append(f"{i}@{name}:9093")

    # Build YAML structure
    inventory_data = {
        "all": {
            "children": {
                "kafka": {
                    "hosts": hosts,
                    "vars": {
                        "ansible_ssh_common_args": "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
                        "kafka_quorum_voters": ",".join(quorum_voters),
                    }
                }
            }
        }
    }

    # Write inventory
    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    import yaml
    with open(INVENTORY_PATH, "w") as f:
        yaml.dump(inventory_data, f, default_flow_style=False, sort_keys=False)

    print(f"Inventory written to {INVENTORY_PATH}")
    print(f"Hosts: {', '.join(hosts.keys())}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Lima Kafka cluster management")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create command
    create_parser = subparsers.add_parser("create", help="Create Kafka VMs")
    create_parser.add_argument("--nodes", type=int, default=1, help="Number of nodes (default: 1)")

    # destroy command
    subparsers.add_parser("destroy", help="Destroy all Kafka VMs")

    # status command
    subparsers.add_parser("status", help="Show VM status")

    # inventory command
    subparsers.add_parser("inventory", help="Generate Ansible inventory")

    args = parser.parse_args()

    if args.command == "create":
        create(nodes=args.nodes)
    elif args.command == "destroy":
        destroy()
    elif args.command == "status":
        status()
    elif args.command == "inventory":
        inventory()


if __name__ == "__main__":
    main()
```

**Step 2: Make executable**

```bash
chmod +x tests/lima/cluster.py
```

**Step 3: Commit**

```bash
git add tests/lima/cluster.py
git commit -m "feat(lima): add Python cluster management CLI"
```

---

## Task 6: Create disk_mount Role Structure

**Files:**
- Create: `roles/disk_mount/defaults/main.yml`
- Create: `roles/disk_mount/tasks/main.yml`
- Create: `roles/disk_mount/handlers/main.yml`
- Create: `roles/disk_mount/meta/main.yml`

**Step 1: Create role directories**

```bash
mkdir -p roles/disk_mount/{defaults,tasks,handlers,meta}
```

**Step 2: Create defaults/main.yml**

```yaml
---
# Disk mount role defaults

# Target disk device (empty = auto-detect largest unformatted disk)
disk_mount_device: ""

# Mount configuration
disk_mount_path: "/data/kafka"
disk_mount_fstype: "xfs"
disk_mount_opts: "noatime,nodiratime"

# Ownership (created after kafka user exists)
disk_mount_owner: "kafka"
disk_mount_group: "kafka"
disk_mount_mode: "0750"

# Safety: set to true to format even if filesystem exists
disk_mount_force_format: false
```

**Step 3: Create meta/main.yml**

```yaml
---
galaxy_info:
  author: your_name
  description: Format and mount data disks idempotently
  license: MIT
  min_ansible_version: "2.16"
  platforms:
    - name: Ubuntu
      versions:
        - noble

dependencies: []
```

**Step 4: Create handlers/main.yml**

```yaml
---
# Handlers for disk_mount role
# Currently no handlers needed - all operations are immediate
```

**Step 5: Create tasks/main.yml**

```yaml
---
# Disk mount role - idempotent disk formatting and mounting

- name: Install filesystem tools
  ansible.builtin.apt:
    name:
      - xfsprogs
      - parted
    state: present
    update_cache: true
    cache_valid_time: 3600

- name: Auto-detect disk device if not specified
  when: disk_mount_device == ""
  block:
    - name: Get list of block devices
      ansible.builtin.command:
        cmd: lsblk -dnpo NAME,TYPE,FSTYPE,SIZE --bytes
      register: lsblk_output
      changed_when: false

    - name: Find largest unformatted disk
      ansible.builtin.set_fact:
        disk_mount_device: >-
          {{ lsblk_output.stdout_lines
             | map('split')
             | selectattr('1', 'equalto', 'disk')
             | selectattr('2', 'equalto', '')
             | sort(attribute='3', reverse=true)
             | map(attribute='0')
             | first
             | default('') }}

    - name: Fail if no unformatted disk found
      ansible.builtin.fail:
        msg: "No unformatted disk found for auto-detection"
      when: disk_mount_device == ""

- name: Display target disk
  ansible.builtin.debug:
    msg: "Target disk: {{ disk_mount_device }}"

- name: Check if disk has filesystem
  ansible.builtin.command:
    cmd: "blkid -o value -s TYPE {{ disk_mount_device }}"
  register: disk_fstype
  changed_when: false
  failed_when: false

- name: Check if disk is mounted
  ansible.builtin.command:
    cmd: "findmnt -n -o TARGET {{ disk_mount_device }}"
  register: disk_mountpoint
  changed_when: false
  failed_when: false

- name: Format disk if unformatted
  when: >
    disk_fstype.stdout == "" or
    (disk_mount_force_format and disk_mountpoint.stdout == "")
  block:
    - name: Create filesystem on disk
      community.general.filesystem:
        dev: "{{ disk_mount_device }}"
        fstype: "{{ disk_mount_fstype }}"
        force: "{{ disk_mount_force_format }}"

- name: Create mount point directory
  ansible.builtin.file:
    path: "{{ disk_mount_path }}"
    state: directory
    mode: "0755"

- name: Check current fstab entry
  ansible.builtin.command:
    cmd: "grep -c '{{ disk_mount_device }}' /etc/fstab"
  register: fstab_check
  changed_when: false
  failed_when: false

- name: Add fstab entry if missing
  ansible.posix.mount:
    path: "{{ disk_mount_path }}"
    src: "{{ disk_mount_device }}"
    fstype: "{{ disk_mount_fstype }}"
    opts: "{{ disk_mount_opts }}"
    state: mounted
  when: fstab_check.stdout == "0" or disk_mountpoint.stdout != disk_mount_path

- name: Ensure disk is mounted
  ansible.posix.mount:
    path: "{{ disk_mount_path }}"
    src: "{{ disk_mount_device }}"
    fstype: "{{ disk_mount_fstype }}"
    opts: "{{ disk_mount_opts }}"
    state: mounted

- name: Set mount point ownership
  ansible.builtin.file:
    path: "{{ disk_mount_path }}"
    owner: "{{ disk_mount_owner }}"
    group: "{{ disk_mount_group }}"
    mode: "{{ disk_mount_mode }}"
    state: directory
  when: disk_mount_owner != ""
```

**Step 6: Commit**

```bash
git add roles/disk_mount
git commit -m "feat(roles): add disk_mount role for idempotent disk formatting"
```

---

## Task 7: Update Taskfile.yml

**Files:**
- Modify: `Taskfile.yml`

**Step 1: Update Taskfile.yml**

Replace the current content with:

```yaml
version: '3'

vars:
  LIMA_DIR: ./tests/lima
  INVENTORY_LIMA: ./inventories/lima/hosts.yml
  INVENTORY_PROD: ./inventories/production/hosts.yml

includes:
  ansible: ./.taskfiles/ansible.yml
  test: ./.taskfiles/test.yml
  test:infra: ./.taskfiles/test-infra.yml

tasks:
  default:
    desc: Show available tasks
    cmds:
      - task --list
```

**Step 2: Commit**

```bash
git add Taskfile.yml
git commit -m "chore(taskfile): update vars for Lima infrastructure"
```

---

## Task 8: Update test-infra.yml for Lima

**Files:**
- Modify: `.taskfiles/test-infra.yml`

**Step 1: Replace test-infra.yml content**

```yaml
version: '3'

vars:
  LIMA_DIR: ./tests/lima

tasks:
  up:
    desc: Create Lima test VMs (use -- --nodes N for multiple)
    dir: "{{.LIMA_DIR}}"
    cmds:
      - uv run cluster.py create {{.CLI_ARGS}}
      - uv run cluster.py inventory
    sources:
      - kafka-node.yaml
      - cluster.py

  down:
    desc: Destroy Lima test VMs
    dir: "{{.LIMA_DIR}}"
    cmds:
      - uv run cluster.py destroy

  status:
    desc: Show Lima VM status
    dir: "{{.LIMA_DIR}}"
    cmds:
      - uv run cluster.py status

  ssh:
    desc: "SSH into a test VM (usage: task test:infra:ssh -- 1)"
    cmds:
      - limactl shell kafka-{{.CLI_ARGS | default "1"}}

  inventory:
    desc: Regenerate Ansible inventory from running VMs
    dir: "{{.LIMA_DIR}}"
    cmds:
      - uv run cluster.py inventory
```

**Step 2: Commit**

```bash
git add .taskfiles/test-infra.yml
git commit -m "feat(taskfile): replace Terraform with Lima in test-infra"
```

---

## Task 9: Update test.yml for Lima

**Files:**
- Modify: `.taskfiles/test.yml`

**Step 1: Replace test.yml content**

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

  quick:
    desc: Quick test (deploy → verify, assumes VMs exist)
    cmds:
      - task: ":ansible:deploy"
      - task: ":ansible:verify"

  converge:
    desc: Just deploy (alias for ansible:deploy)
    cmds:
      - task: ":ansible:deploy"

  wait-for-ssh:
    desc: Wait for SSH to be available on all hosts
    cmds:
      - |
        echo "Waiting for SSH to be available..."
        INVENTORY=./inventories/lima/hosts.yml
        if [ ! -f "$INVENTORY" ]; then
          echo "Inventory not found at $INVENTORY"
          exit 1
        fi

        # Extract hosts and ports from YAML inventory
        HOSTS=$(grep -A2 "ansible_host:" $INVENTORY | grep -E "ansible_host|ansible_port" | paste - - | awk '{print $2 ":" $4}')

        for HOSTPORT in $HOSTS; do
          HOST=$(echo $HOSTPORT | cut -d: -f1)
          PORT=$(echo $HOSTPORT | cut -d: -f2)
          echo -n "Waiting for $HOST:$PORT... "
          for i in $(seq 1 30); do
            if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -p $PORT $USER@$HOST exit 2>/dev/null; then
              echo "ready"
              break
            fi
            if [ $i -eq 30 ]; then
              echo "timeout"
              exit 1
            fi
            sleep 2
          done
        done
        echo "All hosts ready"
    silent: true
```

**Step 2: Commit**

```bash
git add .taskfiles/test.yml
git commit -m "feat(taskfile): update test.yml for Lima inventory"
```

---

## Task 10: Update ansible.yml Default Inventory

**Files:**
- Modify: `.taskfiles/ansible.yml:4`

**Step 1: Update default inventory path**

Change line 4 from:

```yaml
  INVENTORY: '{{.INVENTORY | default "./inventories/test/hosts.yml"}}'
```

To:

```yaml
  INVENTORY: '{{.INVENTORY | default "./inventories/lima/hosts.yml"}}'
```

**Step 2: Commit**

```bash
git add .taskfiles/ansible.yml
git commit -m "chore(taskfile): update default inventory to lima"
```

---

## Task 11: Update kafka Role to Depend on disk_mount

**Files:**
- Modify: `roles/kafka/meta/main.yml`

**Step 1: Add disk_mount dependency**

Update `roles/kafka/meta/main.yml`:

```yaml
---
galaxy_info:
  author: your_name
  description: Install and configure Apache Kafka in KRaft mode
  license: MIT
  min_ansible_version: "2.16"
  platforms:
    - name: Ubuntu
      versions:
        - noble

dependencies:
  - role: disk_mount
  - role: java
```

**Step 2: Commit**

```bash
git add roles/kafka/meta/main.yml
git commit -m "feat(kafka): add disk_mount role dependency"
```

---

## Task 12: Test Lima Infrastructure

**Step 1: Create single VM**

```bash
task test:infra:up
```

Expected: VM created and inventory generated

**Step 2: Check status**

```bash
task test:infra:status
```

Expected: Shows running kafka-1 VM

**Step 3: Verify inventory**

```bash
cat inventories/lima/hosts.yml
```

Expected: Valid YAML with kafka-1 host

**Step 4: Test SSH**

```bash
task test:infra:ssh -- 1
```

Expected: SSH into VM works

**Step 5: Check unformatted disk in VM**

```bash
limactl shell kafka-1 -- lsblk
```

Expected: Shows `/dev/vdb` with no filesystem

**Step 6: Destroy VM**

```bash
task test:infra:down
```

Expected: VM deleted

---

## Task 13: Integration Test

**Step 1: Create VM and run full deployment**

```bash
task test:infra:up
task ansible:deploy
```

Expected: All roles execute successfully including disk_mount

**Step 2: Verify disk is mounted**

```bash
limactl shell kafka-1 -- df -h /data/kafka
```

Expected: Shows mounted xfs filesystem

**Step 3: Verify Kafka service**

```bash
limactl shell kafka-1 -- systemctl status kafka
```

Expected: Kafka service running

**Step 4: Cleanup**

```bash
task test:infra:down
```

**Step 5: Final commit**

```bash
git add -A
git commit -m "test: verify Lima infrastructure and disk_mount role"
```

---

## Summary

After completing all tasks:

1. Terraform/Vultr infrastructure removed
2. Lima infrastructure created with Python CLI
3. disk_mount role created for idempotent disk handling
4. Taskfiles updated for Lima workflow
5. Full integration tested

**Commands available:**

```bash
task test:infra:up              # Create VM(s)
task test:infra:up -- --nodes 3 # Create 3-node cluster
task test:infra:down            # Destroy VMs
task test:infra:status          # Show VM status
task test:infra:ssh -- 1        # SSH into kafka-1
task test:full                  # Full test cycle
```
