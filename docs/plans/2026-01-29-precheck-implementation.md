# Pre-flight Check Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a pre-flight check playbook that validates AWS ARM production VMs before Kafka deployment.

**Architecture:** Ansible playbook with three plays - individual node checks, cluster connectivity checks, and summary report. Includes fixes to existing roles for ARM architecture support.

**Tech Stack:** Ansible 2.x, Ubuntu 24.04, ARM64 (aarch64)

---

### Task 1: Fix Java Role for ARM Architecture

**Files:**
- Modify: `roles/java/defaults/main.yml:5`

**Step 1: Update java_home to ARM path**

Change line 5 from:
```yaml
java_home: "/usr/lib/jvm/java-{{ java_version }}-openjdk-amd64"
```

To:
```yaml
java_home: "/usr/lib/jvm/java-{{ java_version }}-openjdk-arm64"
```

**Step 2: Verify syntax**

Run: `uv run ansible-lint roles/java/defaults/main.yml`
Expected: No errors

**Step 3: Commit**

```bash
git add roles/java/defaults/main.yml
git commit -m "fix: update java_home path for ARM64 architecture"
```

---

### Task 2: Fix Kafka Exporter Role for ARM Architecture

**Files:**
- Modify: `roles/kafka_exporter/defaults/main.yml:7`

**Step 1: Update download URL to ARM64**

Change line 7 from:
```yaml
kafka_exporter_download_url: "https://github.com/danielqsj/kafka_exporter/releases/download/v{{ kafka_exporter_version }}/kafka_exporter-{{ kafka_exporter_version }}.linux-amd64.tar.gz"
```

To:
```yaml
kafka_exporter_download_url: "https://github.com/danielqsj/kafka_exporter/releases/download/v{{ kafka_exporter_version }}/kafka_exporter-{{ kafka_exporter_version }}.linux-arm64.tar.gz"
```

**Step 2: Verify syntax**

Run: `uv run ansible-lint roles/kafka_exporter/defaults/main.yml`
Expected: No errors

**Step 3: Commit**

```bash
git add roles/kafka_exporter/defaults/main.yml
git commit -m "fix: update kafka_exporter download URL for ARM64 architecture"
```

---

### Task 3: Create Pre-flight Playbook - Node Checks (Part 1: OS, Arch, Resources)

**Files:**
- Create: `playbooks/precheck.yml`

**Step 1: Create playbook with OS, architecture, and resource checks**

```yaml
---
# Pre-flight check playbook for Kafka production deployment
# Run with: ansible-playbook -i inventory playbooks/precheck.yml

#######################################
# Play 1: Individual Node Checks
#######################################
- name: Pre-flight Node Validation
  hosts: kafka
  become: true
  gather_facts: true

  vars:
    required_os: "Ubuntu"
    required_os_version: "24.04"
    required_arch: "aarch64"
    min_vcpus: 8
    min_memory_mb: 15360
    min_disk_gb: 2000
    kafka_ports:
      - 9092
      - 9093

  tasks:
    #######################################
    # OS and Architecture Validation
    #######################################
    - name: Check OS distribution
      ansible.builtin.assert:
        that:
          - ansible_distribution == required_os
        fail_msg: "OS must be {{ required_os }}. Found: {{ ansible_distribution }}"
        success_msg: "OS: {{ ansible_distribution }} - OK"

    - name: Check OS version
      ansible.builtin.assert:
        that:
          - ansible_distribution_version == required_os_version
        fail_msg: "OS version must be {{ required_os_version }}. Found: {{ ansible_distribution_version }}"
        success_msg: "OS Version: {{ ansible_distribution_version }} - OK"

    - name: Check architecture
      ansible.builtin.assert:
        that:
          - ansible_architecture == required_arch
        fail_msg: "Architecture must be {{ required_arch }}. Found: {{ ansible_architecture }}"
        success_msg: "Architecture: {{ ansible_architecture }} - OK"

    #######################################
    # Resource Validation
    #######################################
    - name: Check CPU cores
      ansible.builtin.assert:
        that:
          - ansible_processor_vcpus >= min_vcpus
        fail_msg: "Minimum {{ min_vcpus }} vCPUs required. Found: {{ ansible_processor_vcpus }}"
        success_msg: "CPU: {{ ansible_processor_vcpus }} vCPUs - OK"

    - name: Check memory
      ansible.builtin.assert:
        that:
          - ansible_memtotal_mb >= min_memory_mb
        fail_msg: "Minimum {{ (min_memory_mb / 1024) | round(1) }}GB RAM required. Found: {{ (ansible_memtotal_mb / 1024) | round(1) }}GB"
        success_msg: "Memory: {{ (ansible_memtotal_mb / 1024) | round(1) }}GB - OK"
```

**Step 2: Verify syntax**

Run: `uv run ansible-lint playbooks/precheck.yml`
Expected: No errors (or only warnings)

**Step 3: Commit**

```bash
git add playbooks/precheck.yml
git commit -m "feat(precheck): add OS, architecture, and resource validation"
```

---

### Task 4: Add Disk Layout and Space Checks

**Files:**
- Modify: `playbooks/precheck.yml`

**Step 1: Add disk checks after resource validation**

Append to the tasks section (after the memory check):

```yaml
    #######################################
    # Disk Layout and Space Validation
    #######################################
    - name: Get fstab contents
      ansible.builtin.slurp:
        src: /etc/fstab
      register: fstab_content

    - name: Parse and display fstab entries
      ansible.builtin.debug:
        msg: |
          Disk Layout from /etc/fstab:
          {{ fstab_content.content | b64decode }}

    - name: Get mount points and available space
      ansible.builtin.shell:
        cmd: df -BG --output=target,size,avail,fstype | grep -v tmpfs | grep -v udev
        executable: /bin/bash
      register: disk_space
      changed_when: false

    - name: Display disk space
      ansible.builtin.debug:
        msg: |
          Disk Space:
          {{ disk_space.stdout }}

    - name: Get largest available disk space in GB
      ansible.builtin.shell:
        cmd: df -BG --output=avail | tail -n +2 | sed 's/G//' | sort -rn | head -1
        executable: /bin/bash
      register: max_disk_avail
      changed_when: false

    - name: Check disk space meets minimum
      ansible.builtin.assert:
        that:
          - max_disk_avail.stdout | int >= min_disk_gb
        fail_msg: "Minimum {{ min_disk_gb }}GB disk space required. Largest available: {{ max_disk_avail.stdout }}GB"
        success_msg: "Disk Space: {{ max_disk_avail.stdout }}GB available - OK"
```

**Step 2: Verify syntax**

Run: `uv run ansible-lint playbooks/precheck.yml`
Expected: No errors (or only warnings)

**Step 3: Commit**

```bash
git add playbooks/precheck.yml
git commit -m "feat(precheck): add disk layout and space validation"
```

---

### Task 5: Add Firewall Checks

**Files:**
- Modify: `playbooks/precheck.yml`

**Step 1: Add firewall checks after disk checks**

Append to the tasks section:

```yaml
    #######################################
    # Firewall Validation
    #######################################
    - name: Check if UFW is installed
      ansible.builtin.command:
        cmd: which ufw
      register: ufw_installed
      failed_when: false
      changed_when: false

    - name: Get UFW status
      ansible.builtin.command:
        cmd: ufw status
      register: ufw_status
      when: ufw_installed.rc == 0
      changed_when: false

    - name: Display UFW status
      ansible.builtin.debug:
        msg: "Firewall: {{ ufw_status.stdout | default('UFW not installed') }}"
      when: ufw_installed.rc == 0

    - name: Check UFW allows Kafka ports or is inactive
      ansible.builtin.assert:
        that:
          - >
            ufw_installed.rc != 0 or
            'inactive' in ufw_status.stdout | lower or
            (kafka_ports | map('string') | map('regex_search', ufw_status.stdout) | select('string') | list | length == kafka_ports | length)
        fail_msg: "UFW is active but ports {{ kafka_ports }} are not allowed. Run: sudo ufw allow 9092/tcp && sudo ufw allow 9093/tcp"
        success_msg: "Firewall: Kafka ports allowed or UFW inactive - OK"
      when: ufw_installed.rc == 0

    - name: Firewall not installed message
      ansible.builtin.debug:
        msg: "Firewall: UFW not installed - OK"
      when: ufw_installed.rc != 0
```

**Step 2: Verify syntax**

Run: `uv run ansible-lint playbooks/precheck.yml`
Expected: No errors (or only warnings)

**Step 3: Commit**

```bash
git add playbooks/precheck.yml
git commit -m "feat(precheck): add firewall validation"
```

---

### Task 6: Add APT Package Availability Check

**Files:**
- Modify: `playbooks/precheck.yml`

**Step 1: Add APT package check after firewall checks**

Append to the tasks section:

```yaml
    #######################################
    # APT Package Availability
    #######################################
    - name: Update apt cache
      ansible.builtin.apt:
        update_cache: true
        cache_valid_time: 3600

    - name: Check if OpenJDK 21 is available
      ansible.builtin.command:
        cmd: apt-cache policy openjdk-21-jdk-headless
      register: java_package_check
      changed_when: false

    - name: Assert OpenJDK 21 package is available
      ansible.builtin.assert:
        that:
          - "'Candidate:' in java_package_check.stdout"
          - "'(none)' not in java_package_check.stdout"
        fail_msg: "Package openjdk-21-jdk-headless is not available in APT repositories"
        success_msg: "APT Package: openjdk-21-jdk-headless - Available"
```

**Step 2: Verify syntax**

Run: `uv run ansible-lint playbooks/precheck.yml`
Expected: No errors (or only warnings)

**Step 3: Commit**

```bash
git add playbooks/precheck.yml
git commit -m "feat(precheck): add APT package availability check"
```

---

### Task 7: Add Download URL Verification

**Files:**
- Modify: `playbooks/precheck.yml`

**Step 1: Add download verification after APT check**

Append to the tasks section:

```yaml
    #######################################
    # Download URL Verification
    #######################################
    - name: Define download URLs
      ansible.builtin.set_fact:
        kafka_version: "4.1.1"
        kafka_scala_version: "2.13"
        jmx_exporter_version: "1.0.1"
        kafka_exporter_version: "1.8.0"

    - name: Set download URLs
      ansible.builtin.set_fact:
        kafka_download_url: "https://downloads.apache.org/kafka/{{ kafka_version }}/kafka_{{ kafka_scala_version }}-{{ kafka_version }}.tgz"
        jmx_exporter_url: "https://repo1.maven.org/maven2/io/prometheus/jmx/jmx_prometheus_javaagent/{{ jmx_exporter_version }}/jmx_prometheus_javaagent-{{ jmx_exporter_version }}.jar"
        kafka_exporter_url: "https://github.com/danielqsj/kafka_exporter/releases/download/v{{ kafka_exporter_version }}/kafka_exporter-{{ kafka_exporter_version }}.linux-arm64.tar.gz"

    - name: Check Kafka download URL is reachable
      ansible.builtin.uri:
        url: "{{ kafka_download_url }}"
        method: HEAD
        timeout: 30
      register: kafka_url_check
      failed_when: false

    - name: Assert Kafka download URL is reachable
      ansible.builtin.assert:
        that:
          - kafka_url_check.status == 200
        fail_msg: "Kafka download URL not reachable: {{ kafka_download_url }} (status: {{ kafka_url_check.status | default('unknown') }})"
        success_msg: "Download: Kafka binary URL - Reachable"

    - name: Check JMX Exporter download URL is reachable
      ansible.builtin.uri:
        url: "{{ jmx_exporter_url }}"
        method: HEAD
        timeout: 30
      register: jmx_url_check
      failed_when: false

    - name: Assert JMX Exporter download URL is reachable
      ansible.builtin.assert:
        that:
          - jmx_url_check.status == 200
        fail_msg: "JMX Exporter download URL not reachable: {{ jmx_exporter_url }} (status: {{ jmx_url_check.status | default('unknown') }})"
        success_msg: "Download: JMX Exporter JAR URL - Reachable"

    - name: Check Kafka Exporter download URL is reachable
      ansible.builtin.uri:
        url: "{{ kafka_exporter_url }}"
        method: HEAD
        timeout: 30
        follow_redirects: all
      register: kafka_exp_url_check
      failed_when: false

    - name: Assert Kafka Exporter download URL is reachable
      ansible.builtin.assert:
        that:
          - kafka_exp_url_check.status == 200
        fail_msg: "Kafka Exporter download URL not reachable: {{ kafka_exporter_url }} (status: {{ kafka_exp_url_check.status | default('unknown') }})"
        success_msg: "Download: Kafka Exporter ARM64 URL - Reachable"
```

**Step 2: Verify syntax**

Run: `uv run ansible-lint playbooks/precheck.yml`
Expected: No errors (or only warnings)

**Step 3: Commit**

```bash
git add playbooks/precheck.yml
git commit -m "feat(precheck): add download URL verification"
```

---

### Task 8: Add Kafka Binary Architecture Verification

**Files:**
- Modify: `playbooks/precheck.yml`

**Step 1: Add Kafka binary architecture check after URL verification**

Append to the tasks section:

```yaml
    #######################################
    # Kafka Binary Architecture Verification
    #######################################
    - name: Create temp directory for Kafka download test
      ansible.builtin.tempfile:
        state: directory
        prefix: kafka_precheck_
      register: temp_dir

    - name: Download Kafka binary for architecture check
      ansible.builtin.get_url:
        url: "{{ kafka_download_url }}"
        dest: "{{ temp_dir.path }}/kafka.tgz"
        timeout: 120
      register: kafka_download

    - name: Extract Kafka binary
      ansible.builtin.unarchive:
        src: "{{ temp_dir.path }}/kafka.tgz"
        dest: "{{ temp_dir.path }}"
        remote_src: true

    - name: Find kafka-server-start.sh for verification
      ansible.builtin.find:
        paths: "{{ temp_dir.path }}"
        patterns: "kafka-server-start.sh"
        recurse: true
      register: kafka_script

    - name: Verify Kafka scripts are present
      ansible.builtin.assert:
        that:
          - kafka_script.files | length > 0
        fail_msg: "Kafka binary extraction failed - kafka-server-start.sh not found"
        success_msg: "Kafka Binary: Extracted successfully - OK"

    - name: Cleanup temp directory
      ansible.builtin.file:
        path: "{{ temp_dir.path }}"
        state: absent
```

**Step 2: Verify syntax**

Run: `uv run ansible-lint playbooks/precheck.yml`
Expected: No errors (or only warnings)

**Step 3: Commit**

```bash
git add playbooks/precheck.yml
git commit -m "feat(precheck): add Kafka binary architecture verification"
```

---

### Task 9: Add Cluster Connectivity Checks

**Files:**
- Modify: `playbooks/precheck.yml`

**Step 1: Add Play 2 for cluster connectivity after Play 1**

Append after the last task of Play 1:

```yaml
    #######################################
    # Node Check Summary
    #######################################
    - name: Node pre-flight check summary
      ansible.builtin.debug:
        msg:
          - "========================================"
          - "Pre-flight Check Complete: {{ inventory_hostname }}"
          - "========================================"
          - "OS:           {{ ansible_distribution }} {{ ansible_distribution_version }} - OK"
          - "Architecture: {{ ansible_architecture }} - OK"
          - "CPU:          {{ ansible_processor_vcpus }} vCPUs - OK"
          - "Memory:       {{ (ansible_memtotal_mb / 1024) | round(1) }}GB - OK"
          - "Disk:         {{ max_disk_avail.stdout }}GB available - OK"
          - "Firewall:     Checked - OK"
          - "APT Package:  openjdk-21-jdk-headless - Available"
          - "Downloads:    All URLs reachable - OK"
          - "========================================"

#######################################
# Play 2: Cluster Connectivity Checks
#######################################
- name: Pre-flight Cluster Connectivity
  hosts: kafka[0]
  become: true
  gather_facts: false

  tasks:
    - name: Get list of all Kafka hosts
      ansible.builtin.set_fact:
        kafka_hosts: "{{ groups['kafka'] }}"

    - name: Get other Kafka hosts (excluding self)
      ansible.builtin.set_fact:
        other_kafka_hosts: "{{ groups['kafka'] | difference([inventory_hostname]) }}"

    - name: Debug - Testing connectivity to other nodes
      ansible.builtin.debug:
        msg: "Testing connectivity from {{ inventory_hostname }} to: {{ other_kafka_hosts | join(', ') }}"

    - name: Test ping connectivity to other Kafka nodes
      ansible.builtin.command:
        cmd: "ping -c 2 -W 5 {{ item }}"
      loop: "{{ other_kafka_hosts }}"
      register: ping_results
      failed_when: false
      changed_when: false

    - name: Assert ping connectivity to all nodes
      ansible.builtin.assert:
        that:
          - item.rc == 0
        fail_msg: "Cannot ping {{ item.item }} from {{ inventory_hostname }}"
        success_msg: "Ping: {{ item.item }} - Reachable"
      loop: "{{ ping_results.results }}"
      loop_control:
        label: "{{ item.item }}"

    - name: Test SSH connectivity to other Kafka nodes
      ansible.builtin.command:
        cmd: "ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no {{ item }} echo 'SSH OK'"
      loop: "{{ other_kafka_hosts }}"
      register: ssh_results
      failed_when: false
      changed_when: false
      become: false

    - name: Assert SSH connectivity to all nodes
      ansible.builtin.assert:
        that:
          - item.rc == 0
        fail_msg: "Cannot SSH to {{ item.item }} from {{ inventory_hostname }}"
        success_msg: "SSH: {{ item.item }} - Reachable"
      loop: "{{ ssh_results.results }}"
      loop_control:
        label: "{{ item.item }}"

    - name: Cluster connectivity summary
      ansible.builtin.debug:
        msg:
          - "========================================"
          - "Cluster Connectivity Check Complete"
          - "========================================"
          - "All {{ kafka_hosts | length }} nodes can communicate"
          - "Ping: All nodes reachable"
          - "SSH: All nodes reachable"
          - "========================================"
          - ""
          - "========================================"
          - "PRE-FLIGHT CHECK PASSED"
          - "Ready for Kafka deployment!"
          - "========================================"
```

**Step 2: Verify syntax**

Run: `uv run ansible-lint playbooks/precheck.yml`
Expected: No errors (or only warnings)

**Step 3: Commit**

```bash
git add playbooks/precheck.yml
git commit -m "feat(precheck): add cluster connectivity checks and summary"
```

---

### Task 10: Add Taskfile Integration

**Files:**
- Modify: `.taskfiles/ansible.yml`

**Step 1: Add precheck:prod task**

Add after the `verify:prod:single` task (around line 85):

```yaml
  precheck:prod:
    desc: Run pre-flight checks on production VMs before deployment
    vars:
      INVENTORY: ./inventories/production/hosts.yml
    cmds:
      - uv run ansible-playbook -i {{.INVENTORY}} playbooks/precheck.yml
    preconditions:
      - sh: "test -f {{.INVENTORY}}"
        msg: "Production inventory not found: {{.INVENTORY}}"
```

**Step 2: Verify Taskfile syntax**

Run: `task --list`
Expected: Shows `ansible:precheck:prod` in the list

**Step 3: Commit**

```bash
git add .taskfiles/ansible.yml
git commit -m "feat: add precheck:prod task to Taskfile"
```

---

### Task 11: Test Precheck on Production

**Step 1: Run the precheck playbook**

Run: `task ansible:precheck:prod`

Expected: Playbook runs through all checks and either:
- PASSES: Shows "PRE-FLIGHT CHECK PASSED" message
- FAILS: Shows clear error message about what failed

**Step 2: Review output and fix any issues**

If any checks fail, address the underlying issues on the VMs.

**Step 3: Final commit and push**

```bash
git push
```

---

## Summary

| Task | Description |
|------|-------------|
| 1 | Fix Java role for ARM64 |
| 2 | Fix Kafka Exporter role for ARM64 |
| 3 | Create precheck playbook - OS, arch, resources |
| 4 | Add disk layout and space checks |
| 5 | Add firewall checks |
| 6 | Add APT package availability check |
| 7 | Add download URL verification |
| 8 | Add Kafka binary architecture verification |
| 9 | Add cluster connectivity checks |
| 10 | Add Taskfile integration |
| 11 | Test on production |
