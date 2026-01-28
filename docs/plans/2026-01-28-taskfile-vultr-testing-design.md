# Taskfile + Vultr Testing Infrastructure Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Molecule/Podman testing with Terraform-provisioned Vultr VMs and Taskfile-based workflow.

**Architecture:** Terraform manages disposable test VMs on Vultr, Taskfile orchestrates the test lifecycle, Ansible verify playbook validates deployment.

**Tech Stack:** Taskfile.dev, Terraform (Vultr provider), Ansible

---

## Overview

The Molecule + Podman container-based testing approach has proven problematic with systemd/cgroup compatibility issues. This design replaces it with real VM testing on Vultr, orchestrated via Taskfile.

**Key benefits:**
- Tests against real Ubuntu 24.04 VMs (matches production)
- No container/systemd compatibility issues
- Clean task-based workflow with Taskfile
- Ansible roles remain cloud-agnostic (production can be any cloud)

---

## Directory Structure

```
kafka-ansible/
├── Taskfile.yml              # Main taskfile (includes others)
├── taskfiles/
│   ├── infra.yml             # Terraform tasks
│   ├── ansible.yml           # Playbook tasks
│   └── test.yml              # Combined test workflows
├── terraform/
│   ├── main.tf               # Provider config, VM resources
│   ├── variables.tf          # Configurable inputs
│   ├── outputs.tf            # VM IPs for inventory
│   └── inventory.tpl         # Ansible inventory template
├── inventories/
│   ├── production/           # Real deployment inventory
│   │   └── hosts.yml
│   └── test/                 # Generated test inventory
│       └── hosts.yml
├── playbooks/
│   ├── kafka.yml             # Main deployment playbook
│   └── verify.yml            # Verification playbook
└── roles/                    # Existing ansible roles
```

---

## Taskfile Namespace Structure

### infra: (Terraform/Vultr)
| Task | Description |
|------|-------------|
| `infra:init` | Run terraform init |
| `infra:up` | Create 3 Vultr VMs, generate test inventory |
| `infra:down` | Destroy VMs, remove test inventory |
| `infra:status` | Show VM IPs and status |

### ansible: (Playbook execution)
| Task | Description |
|------|-------------|
| `ansible:lint` | Run ansible-lint on roles/playbooks |
| `ansible:deploy` | Run kafka.yml against inventory |
| `ansible:verify` | Run verify.yml to check deployment |

### test: (Combined workflows)
| Task | Description |
|------|-------------|
| `test:full` | Full cycle: up → deploy → verify → down |
| `test:quick` | Quick iteration: deploy → verify (VMs exist) |

---

## Terraform Infrastructure

### VM Specification
- **Provider:** Vultr
- **Count:** 3 VMs
- **OS:** Ubuntu 24.04 LTS
- **Size:** `vc2-1c-1gb` (~$5/mo each) - minimal for testing
- **Region:** Configurable (default: nearest)
- **Names:** kafka-test-1, kafka-test-2, kafka-test-3

### Generated Inventory
Terraform outputs `inventories/test/hosts.yml` with:
- VM IP addresses
- `kafka_node_id` assignments (1, 2, 3)
- `kafka_quorum_voters` group variable
- SSH connection settings

### State Management
- Local state file (no remote backend)
- State in `terraform/terraform.tfstate`
- Added to `.gitignore`

---

## Verification Playbook

`playbooks/verify.yml` performs these checks:

### 1. Java Verification
- Java binary exists at expected path
- `java -version` returns OpenJDK 21

### 2. Kafka Verification
- kafka user/group exists
- `/opt/kafka` directory with correct ownership
- `server.properties` has correct `node.id` and `quorum.voters`
- `kafka.service` is running and enabled
- Port 9092 (broker) is listening
- Port 9093 (controller) is listening

### 3. Cluster Health
- All 3 nodes can see each other (quorum formed)
- `kafka-metadata.sh` shows healthy cluster state
- Can create a test topic
- Can produce/consume a test message

### 4. Exporters Verification
- JMX Exporter: port 7071 responding with metrics
- Kafka Exporter: port 9308 responding with metrics

---

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `VULTR_API_KEY` | Vultr API key for Terraform | Yes |

SSH key path is configured in `terraform/variables.tf`.

---

## Typical Workflow

```bash
# One-time setup
task infra:init

# Test cycle
task infra:up        # Spin up 3 VMs (~2 min)
task ansible:deploy  # Deploy Kafka cluster
task ansible:verify  # Verify everything works

# Iterate if needed
task ansible:deploy
task ansible:verify

# Clean up
task infra:down      # Tear down VMs
```

Or run the full automated cycle:
```bash
task test:full       # up → deploy → verify → down
```

---

## Notes

- All ansible commands use `uv run` to stay in Python environment
- Test inventory is generated, not committed to git
- Production deployment uses separate `inventories/production/hosts.yml`
- Ansible roles are cloud-agnostic - same roles work for test and production

---

## Implementation Status (2026-01-28)

### Completed ✅
- [x] Taskfile directory structure (`taskfiles/infra.yml`, `ansible.yml`, `test.yml`)
- [x] Main `Taskfile.yml` with namespace includes
- [x] Terraform configuration (`main.tf`, `versions.tf`, `variables.tf`, `outputs.tf`)
- [x] Ansible inventory template (`templates/inventory.tpl`)
- [x] Verification playbook (`playbooks/verify.yml`)
- [x] `terraform init` working
- [x] Code pushed to GitHub: https://github.com/jasoet/kafka-ansible

### Pending ⏳
- [ ] Integration test (VM creation → Kafka deploy → verify → destroy)

### Issues Encountered
1. **Singapore region slow provisioning**: VMs took 38+ minutes and were still in "installing" state. Switched default region to Tokyo (nrt).
2. **Vultr API IP restriction**: API key had IP whitelist enabled. Required adding current IP to allowed list in Vultr settings.

### Configuration
- **Region:** `nrt` (Tokyo, Japan) - changed from `sgp` due to slow provisioning
- **SSH Key ID:** `ed68e543-2daa-4539-82a8-847d2866b006`
- **VM Plan:** `vc2-1c-1gb` (~$5/mo each)
- **OS:** Ubuntu 24.04 LTS (ID: 2284)

### Next Steps
1. Resolve Vultr provisioning issues
2. Run full integration test: `task test:full`
3. Verify Kafka cluster deployment works end-to-end
