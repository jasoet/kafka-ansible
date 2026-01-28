# Taskfile + Vultr Testing Infrastructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Taskfile-based workflow with Terraform-provisioned Vultr VMs for testing Kafka Ansible roles.

**Architecture:** Terraform manages 3 disposable Ubuntu 24.04 VMs on Vultr (Singapore region), generates Ansible inventory, Taskfile orchestrates the full test lifecycle (create → deploy → verify → destroy).

**Tech Stack:** Taskfile.dev, Terraform (Vultr provider), Ansible, uv

---

## Context

- **Vultr API Key:** `MYRFCR4S6NWK66DIV72LO6LRYUVRHZ7XN4UQ`
- **SSH Key ID:** `ed68e543-2daa-4539-82a8-847d2866b006`
- **Region:** `sgp` (Singapore)
- **Plan:** `vc2-1c-1gb` ($5/mo per VM)
- **Python tooling:** All commands use `uv run`

---

### Task 1: Create Taskfile Directory Structure

**Files:**
- Create: `taskfiles/infra.yml`
- Create: `taskfiles/ansible.yml`
- Create: `taskfiles/test.yml`

**Step 1: Create taskfiles directory**

```bash
mkdir -p taskfiles
```

**Step 2: Create empty taskfile placeholders**

```bash
touch taskfiles/infra.yml taskfiles/ansible.yml taskfiles/test.yml
```

**Step 3: Commit**

```bash
git add taskfiles/
git commit -m "chore: add taskfiles directory structure"
```

---

### Task 2: Create Main Taskfile.yml

**Files:**
- Create: `Taskfile.yml`

**Step 1: Create main Taskfile**

```yaml
version: '3'

vars:
  TERRAFORM_DIR: ./terraform
  INVENTORY_TEST: ./inventories/test/hosts.yml
  INVENTORY_PROD: ./inventories/production/hosts.yml

includes:
  infra: ./taskfiles/infra.yml
  ansible: ./taskfiles/ansible.yml
  test: ./taskfiles/test.yml

tasks:
  default:
    desc: Show available tasks
    cmds:
      - task --list
```

**Step 2: Verify taskfile syntax**

Run: `task --list`
Expected: Shows "default" task and included namespaces

**Step 3: Commit**

```bash
git add Taskfile.yml
git commit -m "chore: add main Taskfile with namespace includes"
```

---

### Task 3: Create Terraform Directory and Provider Config

**Files:**
- Create: `terraform/main.tf`
- Create: `terraform/versions.tf`

**Step 1: Create terraform directory**

```bash
mkdir -p terraform
```

**Step 2: Create versions.tf with provider requirements**

```hcl
terraform {
  required_version = ">= 1.0"

  required_providers {
    vultr = {
      source  = "vultr/vultr"
      version = "~> 2.19"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}
```

**Step 3: Create main.tf with provider config**

```hcl
provider "vultr" {
  api_key     = var.vultr_api_key
  rate_limit  = 100
  retry_limit = 3
}
```

**Step 4: Commit**

```bash
git add terraform/
git commit -m "chore: add terraform provider configuration"
```

---

### Task 4: Create Terraform Variables

**Files:**
- Create: `terraform/variables.tf`
- Create: `terraform/terraform.tfvars.example`

**Step 1: Create variables.tf**

```hcl
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
  default     = "sgp"
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
```

**Step 2: Create terraform.tfvars.example**

```hcl
# Copy this to terraform.tfvars and fill in values
vultr_api_key = "your-api-key-here"

# Optional overrides (defaults are fine for testing)
# ssh_key_id     = "your-ssh-key-id"
# region         = "sgp"
# plan           = "vc2-1c-1gb"
# instance_count = 3
```

**Step 3: Update .gitignore for terraform**

Add to `.gitignore`:
```
# Terraform
terraform/.terraform/
terraform/.terraform.lock.hcl
terraform/terraform.tfstate
terraform/terraform.tfstate.backup
terraform/terraform.tfvars
```

**Step 4: Commit**

```bash
git add terraform/variables.tf terraform/terraform.tfvars.example .gitignore
git commit -m "chore: add terraform variables and tfvars example"
```

---

### Task 5: Create Terraform VM Resources

**Files:**
- Modify: `terraform/main.tf`

**Step 1: Add data source for OS**

Append to `terraform/main.tf`:

```hcl
# Get Ubuntu 24.04 LTS OS ID
data "vultr_os" "ubuntu" {
  filter {
    name   = "name"
    values = ["Ubuntu 24.04 LTS x64"]
  }
}
```

**Step 2: Add VM instances resource**

Append to `terraform/main.tf`:

```hcl
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
```

**Step 3: Commit**

```bash
git add terraform/main.tf
git commit -m "feat: add terraform vultr instance resources"
```

---

### Task 6: Create Terraform Outputs and Inventory Template

**Files:**
- Create: `terraform/outputs.tf`
- Create: `terraform/templates/inventory.tpl`

**Step 1: Create templates directory**

```bash
mkdir -p terraform/templates
```

**Step 2: Create inventory template**

```yaml
# terraform/templates/inventory.tpl
---
all:
  children:
    kafka:
      hosts:
%{ for idx, instance in instances ~}
        ${instance.hostname}:
          ansible_host: ${instance.main_ip}
          ansible_user: root
          kafka_node_id: ${idx + 1}
%{ endfor ~}
      vars:
        kafka_quorum_voters: "${quorum_voters}"
```

**Step 3: Create outputs.tf**

```hcl
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
  filename        = "${path.module}/../inventories/test/hosts.yml"
  file_permission = "0644"
}

output "inventory_path" {
  description = "Path to generated inventory file"
  value       = local_file.inventory.filename
}
```

**Step 4: Create test inventory directory**

```bash
mkdir -p inventories/test
echo "# Generated by Terraform - do not edit" > inventories/test/.gitkeep
```

**Step 5: Update .gitignore**

Add to `.gitignore`:
```
# Generated test inventory
inventories/test/hosts.yml
```

**Step 6: Commit**

```bash
git add terraform/outputs.tf terraform/templates/inventory.tpl inventories/test/.gitkeep .gitignore
git commit -m "feat: add terraform outputs and inventory generation"
```

---

### Task 7: Create Infra Taskfile

**Files:**
- Modify: `taskfiles/infra.yml`

**Step 1: Write infra.yml taskfile**

```yaml
version: '3'

vars:
  TF_DIR: ./terraform

tasks:
  init:
    desc: Initialize Terraform
    dir: "{{.TF_DIR}}"
    cmds:
      - terraform init
    status:
      - test -d .terraform

  up:
    desc: Create Vultr test VMs
    dir: "{{.TF_DIR}}"
    deps:
      - init
    cmds:
      - terraform apply -auto-approve
      - echo ""
      - echo "=== Test VMs Created ==="
      - terraform output -json instance_ips | jq -r 'to_entries[] | "\(.key): \(.value)"'
      - echo ""
      - echo "Inventory generated at inventories/test/hosts.yml"
    env:
      TF_VAR_vultr_api_key: "{{.VULTR_API_KEY}}"

  down:
    desc: Destroy Vultr test VMs
    dir: "{{.TF_DIR}}"
    cmds:
      - terraform destroy -auto-approve
      - rm -f ../inventories/test/hosts.yml
      - echo "Test VMs destroyed and inventory removed"
    env:
      TF_VAR_vultr_api_key: "{{.VULTR_API_KEY}}"

  status:
    desc: Show test VM status
    dir: "{{.TF_DIR}}"
    cmds:
      - |
        if [ -f terraform.tfstate ]; then
          echo "=== Test VM Status ==="
          terraform output -json instance_ips 2>/dev/null | jq -r 'to_entries[] | "\(.key): \(.value)"' || echo "No VMs running"
        else
          echo "No Terraform state found. Run 'task infra:up' first."
        fi

  ssh:
    desc: SSH into a test VM (usage: task infra:ssh -- kafka-test-1)
    dir: "{{.TF_DIR}}"
    cmds:
      - |
        HOST={{.CLI_ARGS}}
        if [ -z "$HOST" ]; then
          HOST="kafka-test-1"
        fi
        IP=$(terraform output -json instance_ips | jq -r ".[\"$HOST\"]")
        if [ "$IP" != "null" ] && [ -n "$IP" ]; then
          ssh -o StrictHostKeyChecking=no root@$IP
        else
          echo "Host $HOST not found. Available hosts:"
          terraform output -json instance_ips | jq -r 'keys[]'
        fi
```

**Step 2: Verify task list**

Run: `task infra:init --dry`
Expected: Shows terraform init command

**Step 3: Commit**

```bash
git add taskfiles/infra.yml
git commit -m "feat: add infra taskfile for terraform operations"
```

---

### Task 8: Create Ansible Taskfile

**Files:**
- Modify: `taskfiles/ansible.yml`

**Step 1: Write ansible.yml taskfile**

```yaml
version: '3'

vars:
  INVENTORY: "{{.INVENTORY | default \"./inventories/test/hosts.yml\"}}"

tasks:
  lint:
    desc: Run ansible-lint on roles and playbooks
    cmds:
      - uv run ansible-lint roles/ playbooks/

  ping:
    desc: Ping all hosts in inventory
    cmds:
      - uv run ansible -i {{.INVENTORY}} all -m ping

  facts:
    desc: Gather facts from all hosts
    cmds:
      - uv run ansible -i {{.INVENTORY}} all -m setup

  deploy:
    desc: Deploy Kafka cluster
    cmds:
      - uv run ansible-playbook -i {{.INVENTORY}} playbooks/kafka.yml
    preconditions:
      - test -f {{.INVENTORY}}
      - sh: "test -f {{.INVENTORY}}"
        msg: "Inventory file not found: {{.INVENTORY}}. Run 'task infra:up' first."

  verify:
    desc: Verify Kafka cluster deployment
    cmds:
      - uv run ansible-playbook -i {{.INVENTORY}} playbooks/verify.yml
    preconditions:
      - sh: "test -f {{.INVENTORY}}"
        msg: "Inventory file not found: {{.INVENTORY}}. Run 'task infra:up' first."

  deploy:prod:
    desc: Deploy to production (requires confirmation)
    vars:
      INVENTORY: ./inventories/production/hosts.yml
    cmds:
      - uv run ansible-playbook -i {{.INVENTORY}} playbooks/kafka.yml
    preconditions:
      - sh: "test -f {{.INVENTORY}}"
        msg: "Production inventory not found: {{.INVENTORY}}"
    prompt: "Deploy to PRODUCTION? This will modify production servers."
```

**Step 2: Verify task list**

Run: `task ansible:lint --dry`
Expected: Shows ansible-lint command

**Step 3: Commit**

```bash
git add taskfiles/ansible.yml
git commit -m "feat: add ansible taskfile for playbook operations"
```

---

### Task 9: Create Test Taskfile

**Files:**
- Modify: `taskfiles/test.yml`

**Step 1: Write test.yml taskfile**

```yaml
version: '3'

tasks:
  full:
    desc: Full test cycle (up → deploy → verify → down)
    cmds:
      - task: infra:up
      - task: wait-for-ssh
      - task: ansible:deploy
      - task: ansible:verify
      - defer: { task: infra:down }
    env:
      VULTR_API_KEY: "{{.VULTR_API_KEY}}"

  quick:
    desc: Quick test (deploy → verify, assumes VMs exist)
    cmds:
      - task: ansible:deploy
      - task: ansible:verify

  converge:
    desc: Just deploy (alias for ansible:deploy)
    cmds:
      - task: ansible:deploy

  wait-for-ssh:
    desc: Wait for SSH to be available on all hosts
    cmds:
      - |
        echo "Waiting for SSH to be available..."
        INVENTORY=./inventories/test/hosts.yml
        if [ ! -f "$INVENTORY" ]; then
          echo "Inventory not found"
          exit 1
        fi
        HOSTS=$(grep "ansible_host:" $INVENTORY | awk '{print $2}')
        for HOST in $HOSTS; do
          echo -n "Waiting for $HOST... "
          for i in $(seq 1 30); do
            if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes root@$HOST exit 2>/dev/null; then
              echo "ready"
              break
            fi
            if [ $i -eq 30 ]; then
              echo "timeout"
              exit 1
            fi
            sleep 5
          done
        done
        echo "All hosts ready"
    silent: true
```

**Step 2: Verify task list**

Run: `task test:quick --dry`
Expected: Shows deploy and verify commands

**Step 3: Commit**

```bash
git add taskfiles/test.yml
git commit -m "feat: add test taskfile for combined workflows"
```

---

### Task 10: Create Verification Playbook

**Files:**
- Create: `playbooks/verify.yml`

**Step 1: Create verify.yml playbook**

```yaml
---
- name: Verify Kafka Cluster Deployment
  hosts: kafka
  become: true
  gather_facts: true

  tasks:
    # ===================
    # Java Verification
    # ===================
    - name: Verify Java is installed
      ansible.builtin.command: java -version
      register: java_version
      changed_when: false

    - name: Assert Java version is correct
      ansible.builtin.assert:
        that:
          - "'openjdk' in java_version.stderr | lower or 'openjdk' in java_version.stdout | lower"
        fail_msg: "Java is not installed or not OpenJDK"
        success_msg: "Java verification passed"

    # ===================
    # Kafka User/Group
    # ===================
    - name: Verify kafka user exists
      ansible.builtin.getent:
        database: passwd
        key: kafka

    - name: Verify kafka group exists
      ansible.builtin.getent:
        database: group
        key: kafka

    # ===================
    # Kafka Installation
    # ===================
    - name: Verify Kafka directory exists
      ansible.builtin.stat:
        path: /opt/kafka
      register: kafka_dir

    - name: Assert Kafka directory exists
      ansible.builtin.assert:
        that:
          - kafka_dir.stat.exists
          - kafka_dir.stat.isdir
        fail_msg: "Kafka directory /opt/kafka does not exist"
        success_msg: "Kafka directory exists"

    - name: Verify Kafka binaries exist
      ansible.builtin.stat:
        path: "/opt/kafka/bin/{{ item }}"
      loop:
        - kafka-server-start.sh
        - kafka-topics.sh
        - kafka-console-producer.sh
        - kafka-console-consumer.sh
        - kafka-metadata.sh
      register: kafka_binaries

    - name: Assert Kafka binaries exist
      ansible.builtin.assert:
        that:
          - item.stat.exists
        fail_msg: "Kafka binary {{ item.item }} does not exist"
        success_msg: "Kafka binary {{ item.item }} exists"
      loop: "{{ kafka_binaries.results }}"
      loop_control:
        label: "{{ item.item }}"

    # ===================
    # Kafka Configuration
    # ===================
    - name: Verify server.properties exists
      ansible.builtin.stat:
        path: /opt/kafka/config/kraft/server.properties
      register: server_props

    - name: Assert server.properties exists
      ansible.builtin.assert:
        that:
          - server_props.stat.exists
        fail_msg: "server.properties does not exist"
        success_msg: "server.properties exists"

    - name: Check node.id in configuration
      ansible.builtin.shell: grep "^node.id=" /opt/kafka/config/kraft/server.properties
      register: node_id_check
      changed_when: false

    - name: Assert node.id is configured
      ansible.builtin.assert:
        that:
          - node_id_check.stdout | length > 0
        fail_msg: "node.id not configured in server.properties"
        success_msg: "node.id is configured: {{ node_id_check.stdout }}"

    # ===================
    # Kafka Service
    # ===================
    - name: Verify Kafka service is running
      ansible.builtin.systemd:
        name: kafka
      register: kafka_service

    - name: Assert Kafka service is active
      ansible.builtin.assert:
        that:
          - kafka_service.status.ActiveState == "active"
        fail_msg: "Kafka service is not running"
        success_msg: "Kafka service is running"

    - name: Verify Kafka service is enabled
      ansible.builtin.assert:
        that:
          - kafka_service.status.UnitFileState == "enabled"
        fail_msg: "Kafka service is not enabled"
        success_msg: "Kafka service is enabled"

    # ===================
    # Port Verification
    # ===================
    - name: Verify broker port 9092 is listening
      ansible.builtin.wait_for:
        port: 9092
        host: "{{ ansible_default_ipv4.address }}"
        timeout: 10
      register: port_9092

    - name: Verify controller port 9093 is listening
      ansible.builtin.wait_for:
        port: 9093
        host: "{{ ansible_default_ipv4.address }}"
        timeout: 10
      register: port_9093

    # ===================
    # JMX Exporter
    # ===================
    - name: Verify JMX Exporter port 7071 is listening
      ansible.builtin.wait_for:
        port: 7071
        host: "{{ ansible_default_ipv4.address }}"
        timeout: 10

    - name: Check JMX Exporter metrics endpoint
      ansible.builtin.uri:
        url: "http://{{ ansible_default_ipv4.address }}:7071/metrics"
        return_content: false
        status_code: 200
      register: jmx_metrics

    - name: Assert JMX Exporter is responding
      ansible.builtin.assert:
        that:
          - jmx_metrics.status == 200
        fail_msg: "JMX Exporter is not responding on port 7071"
        success_msg: "JMX Exporter is responding"

    # ===================
    # Kafka Exporter
    # ===================
    - name: Verify Kafka Exporter port 9308 is listening
      ansible.builtin.wait_for:
        port: 9308
        host: "{{ ansible_default_ipv4.address }}"
        timeout: 10

    - name: Check Kafka Exporter metrics endpoint
      ansible.builtin.uri:
        url: "http://{{ ansible_default_ipv4.address }}:9308/metrics"
        return_content: false
        status_code: 200
      register: kafka_exporter_metrics

    - name: Assert Kafka Exporter is responding
      ansible.builtin.assert:
        that:
          - kafka_exporter_metrics.status == 200
        fail_msg: "Kafka Exporter is not responding on port 9308"
        success_msg: "Kafka Exporter is responding"

# ===================
# Cluster Health Check (run on first node only)
# ===================
- name: Verify Kafka Cluster Health
  hosts: kafka[0]
  become: true
  gather_facts: false

  tasks:
    - name: Check cluster metadata
      ansible.builtin.shell: |
        /opt/kafka/bin/kafka-metadata.sh --snapshot /data/kafka/__cluster_metadata-0/00000000000000000000.log --command "cat" 2>/dev/null | head -20 || echo "Metadata check completed"
      register: metadata_check
      changed_when: false
      ignore_errors: true

    - name: Create test topic
      ansible.builtin.shell: |
        /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic test-verify --partitions 3 --replication-factor 3 --if-not-exists
      register: create_topic
      changed_when: "'Created' in create_topic.stdout"

    - name: List topics
      ansible.builtin.shell: |
        /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
      register: topic_list
      changed_when: false

    - name: Assert test topic exists
      ansible.builtin.assert:
        that:
          - "'test-verify' in topic_list.stdout"
        fail_msg: "Test topic was not created"
        success_msg: "Test topic exists"

    - name: Produce test message
      ansible.builtin.shell: |
        echo "verification-test-message-$(date +%s)" | /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic test-verify
      changed_when: true

    - name: Consume test message
      ansible.builtin.shell: |
        timeout 10 /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic test-verify --from-beginning --max-messages 1
      register: consume_result
      changed_when: false

    - name: Assert message was consumed
      ansible.builtin.assert:
        that:
          - consume_result.stdout | length > 0
        fail_msg: "Could not consume test message"
        success_msg: "Successfully produced and consumed test message"

    - name: Delete test topic
      ansible.builtin.shell: |
        /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic test-verify
      changed_when: true

    - name: Verification complete
      ansible.builtin.debug:
        msg: |
          ==========================================
          KAFKA CLUSTER VERIFICATION COMPLETE
          ==========================================
          - Java: OK
          - Kafka installation: OK
          - Kafka service: Running
          - Broker port (9092): Listening
          - Controller port (9093): Listening
          - JMX Exporter (7071): Responding
          - Kafka Exporter (9308): Responding
          - Cluster: Healthy (can create topics, produce/consume)
          ==========================================
```

**Step 2: Commit**

```bash
git add playbooks/verify.yml
git commit -m "feat: add verification playbook for kafka cluster"
```

---

### Task 11: Create terraform.tfvars with API Key

**Files:**
- Create: `terraform/terraform.tfvars` (not committed)

**Step 1: Create terraform.tfvars with actual API key**

```hcl
vultr_api_key = "MYRFCR4S6NWK66DIV72LO6LRYUVRHZ7XN4UQ"
```

**Step 2: Verify file is gitignored**

Run: `git status terraform/terraform.tfvars`
Expected: File should not be tracked

**Step 3: No commit (file is gitignored)**

---

### Task 12: Test Terraform Init

**Files:**
- None (testing only)

**Step 1: Run terraform init**

Run: `task infra:init`
Expected: Terraform downloads providers, shows "Terraform has been successfully initialized!"

**Step 2: Verify providers installed**

Run: `ls terraform/.terraform/providers/`
Expected: Shows vultr and local providers

---

### Task 13: Integration Test - Full Cycle

**Files:**
- None (testing only)

**Step 1: Run infra:up to create VMs**

Run: `task infra:up`
Expected:
- Creates 3 Vultr VMs
- Shows IP addresses
- Generates `inventories/test/hosts.yml`

**Step 2: Verify inventory was generated**

Run: `cat inventories/test/hosts.yml`
Expected: Shows 3 hosts with IPs and kafka_node_id

**Step 3: Wait for VMs and test SSH**

Run: `task test:wait-for-ssh`
Expected: All hosts become reachable

**Step 4: Test ansible ping**

Run: `task ansible:ping`
Expected: All 3 hosts respond with pong

**Step 5: Deploy Kafka cluster**

Run: `task ansible:deploy`
Expected: Playbook completes successfully

**Step 6: Verify deployment**

Run: `task ansible:verify`
Expected: All verification checks pass

**Step 7: Destroy test VMs**

Run: `task infra:down`
Expected: VMs destroyed, inventory removed

---

### Task 14: Clean Up and Final Commit

**Files:**
- Modify: `.gitignore` (if needed)
- Delete: `molecule/` directory (optional, no longer needed)

**Step 1: Verify all files are committed**

Run: `git status`
Expected: Working tree clean (except terraform.tfvars which is gitignored)

**Step 2: Optionally remove molecule directory**

```bash
rm -rf molecule/
git add -A
git commit -m "chore: remove molecule directory (replaced by vultr testing)"
```

**Step 3: Final verification**

Run: `task --list`
Expected: Shows all available tasks organized by namespace

---

## Summary

After completing all tasks, you will have:

1. **Taskfile.yml** - Main entrypoint with namespace includes
2. **taskfiles/** - Organized task definitions
   - `infra.yml` - Terraform operations
   - `ansible.yml` - Playbook operations
   - `test.yml` - Combined workflows
3. **terraform/** - Vultr VM provisioning
   - Creates 3 Ubuntu 24.04 VMs
   - Generates Ansible inventory
4. **playbooks/verify.yml** - Comprehensive verification

**Usage:**
```bash
task infra:up        # Create test VMs
task ansible:deploy  # Deploy Kafka
task ansible:verify  # Verify deployment
task infra:down      # Destroy VMs

# Or run full cycle:
task test:full
```
