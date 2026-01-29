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
DISK_PREFIX = "kafka-data"
DISK_SIZE = "10G"


def run_cmd(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def disk_exists(name: str) -> bool:
    """Check if a Lima disk exists."""
    result = run_cmd(["limactl", "disk", "list", "--json"], capture=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return False
    for line in result.stdout.strip().split("\n"):
        if line:
            disk = json.loads(line)
            if disk.get("name") == name:
                return True
    return False


def get_disk_name(vm_index: int) -> str:
    """Get disk name for a VM index."""
    return f"{DISK_PREFIX}-{vm_index}"


def ensure_disk(vm_index: int) -> None:
    """Ensure the data disk for a VM exists, create if not."""
    disk_name = get_disk_name(vm_index)
    if disk_exists(disk_name):
        print(f"Disk '{disk_name}' already exists")
        return
    print(f"Creating disk '{disk_name}' ({DISK_SIZE})...")
    run_cmd(["limactl", "disk", "create", disk_name, "--size", DISK_SIZE, "--format", "raw"])


def delete_disk(vm_index: int) -> None:
    """Delete the data disk for a VM if it exists."""
    disk_name = get_disk_name(vm_index)
    if not disk_exists(disk_name):
        return
    print(f"Deleting disk '{disk_name}'...")
    run_cmd(["limactl", "disk", "delete", disk_name], check=False)


def delete_all_disks() -> None:
    """Delete all kafka data disks."""
    result = run_cmd(["limactl", "disk", "list", "--json"], capture=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return
    for line in result.stdout.strip().split("\n"):
        if line:
            disk = json.loads(line)
            disk_name = disk.get("name", "")
            if disk_name.startswith(DISK_PREFIX):
                print(f"Deleting disk '{disk_name}'...")
                run_cmd(["limactl", "disk", "delete", disk_name], check=False)


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


def generate_vm_template(vm_index: int) -> Path:
    """Generate a VM template with the correct disk name."""
    import yaml

    with open(TEMPLATE_PATH) as f:
        template = yaml.safe_load(f)

    # Update disk name for this VM
    disk_name = get_disk_name(vm_index)
    template["additionalDisks"] = [{"name": disk_name, "format": False}]

    # Write temporary template
    temp_template = TEMPLATE_PATH.parent / f"kafka-node-{vm_index}.yaml"
    with open(temp_template, "w") as f:
        yaml.dump(template, f, default_flow_style=False, sort_keys=False)

    return temp_template


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

        # Ensure disk for this VM exists
        ensure_disk(i)

        # Generate template with correct disk name
        vm_template = generate_vm_template(i)

        # Create VM
        run_cmd([
            "limactl", "create",
            "--name", name,
            "--tty=false",
            str(vm_template)
        ])

        # Clean up temporary template
        vm_template.unlink()

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

    # Delete all data disks
    delete_all_disks()

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
