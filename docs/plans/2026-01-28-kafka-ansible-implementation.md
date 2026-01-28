# Kafka Ansible Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Ansible roles and playbook to deploy a production-ready 3-node Kafka 4.1.1 KRaft cluster with monitoring exporters.

**Architecture:** Four separate roles (java, kafka, jmx_exporter, kafka_exporter) orchestrated by a single playbook. Each role is independently testable with Molecule + Podman. Resource-aware configuration auto-scales with VM specs.

**Tech Stack:** Ansible Core 2.16+, Molecule 6.0+, Podman, uv for Python management, Ubuntu 24.04 target

---

## Task 1: Project Setup - Python Environment

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "kafka-ansible"
version = "0.1.0"
description = "Ansible roles for Kafka KRaft cluster deployment"
requires-python = ">=3.11"

dependencies = [
    "ansible-core>=2.16",
    "ansible-lint>=24.0",
    "molecule>=6.0",
    "molecule-podman>=2.0",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
]
```

**Step 2: Create .python-version**

```
3.12
```

**Step 3: Initialize uv and sync dependencies**

Run: `uv sync`
Expected: Creates `.venv/` and `uv.lock`

**Step 4: Verify ansible is available**

Run: `uv run ansible --version`
Expected: Shows ansible-core 2.16+

**Step 5: Commit**

```bash
git add pyproject.toml .python-version uv.lock
git commit -m "feat: add Python project setup with uv"
```

---

## Task 2: Project Setup - Ansible Configuration

**Files:**
- Create: `ansible.cfg`

**Step 1: Create ansible.cfg**

```ini
[defaults]
inventory = inventories/production/hosts.yml
roles_path = roles
host_key_checking = False
retry_files_enabled = False
gathering = smart
fact_caching = jsonfile
fact_caching_connection = .cache/ansible_facts
fact_caching_timeout = 86400

[privilege_escalation]
become = True
become_method = sudo

[ssh_connection]
pipelining = True
ssh_args = -o ControlMaster=auto -o ControlPersist=60s
```

**Step 2: Create cache directory placeholder**

Run: `mkdir -p .cache && touch .cache/.gitkeep`

**Step 3: Verify ansible config**

Run: `uv run ansible-config dump --only-changed`
Expected: Shows custom settings from ansible.cfg

**Step 4: Commit**

```bash
git add ansible.cfg .cache/.gitkeep
git commit -m "feat: add Ansible configuration"
```

---

## Task 3: Project Setup - Directory Structure

**Files:**
- Create: `roles/.gitkeep`
- Create: `playbooks/.gitkeep`
- Create: `inventories/production/group_vars/.gitkeep`
- Create: `inventories/staging/group_vars/.gitkeep`

**Step 1: Create directory structure**

Run:
```bash
mkdir -p roles playbooks inventories/production/group_vars inventories/staging/group_vars
touch roles/.gitkeep playbooks/.gitkeep inventories/production/group_vars/.gitkeep inventories/staging/group_vars/.gitkeep
```

**Step 2: Commit**

```bash
git add roles playbooks inventories
git commit -m "feat: add project directory structure"
```

---

## Task 4: Java Role - Structure and Variables

**Files:**
- Create: `roles/java/tasks/main.yml`
- Create: `roles/java/defaults/main.yml`
- Create: `roles/java/handlers/main.yml`
- Create: `roles/java/meta/main.yml`

**Step 1: Create role directory structure**

Run: `mkdir -p roles/java/{tasks,defaults,handlers,meta}`

**Step 2: Create defaults/main.yml**

```yaml
---
# Java version configuration
java_version: "21"
java_package: "openjdk-{{ java_version }}-jdk-headless"
java_home: "/usr/lib/jvm/java-{{ java_version }}-openjdk-amd64"
```

**Step 3: Create meta/main.yml**

```yaml
---
galaxy_info:
  author: your_name
  description: Install OpenJDK for Kafka
  license: MIT
  min_ansible_version: "2.16"
  platforms:
    - name: Ubuntu
      versions:
        - noble  # 24.04

dependencies: []
```

**Step 4: Create empty handlers/main.yml**

```yaml
---
# Handlers for java role
```

**Step 5: Create tasks/main.yml (stub)**

```yaml
---
# Java installation tasks
- name: Placeholder
  ansible.builtin.debug:
    msg: "Java role tasks will be implemented"
```

**Step 6: Commit**

```bash
git add roles/java
git commit -m "feat(java): add role structure and variables"
```

---

## Task 5: Java Role - Implementation

**Files:**
- Modify: `roles/java/tasks/main.yml`

**Step 1: Implement Java installation tasks**

Replace `roles/java/tasks/main.yml` with:

```yaml
---
- name: Update apt cache
  ansible.builtin.apt:
    update_cache: true
    cache_valid_time: 3600

- name: Install OpenJDK {{ java_version }}
  ansible.builtin.apt:
    name: "{{ java_package }}"
    state: present

- name: Set JAVA_HOME in /etc/environment
  ansible.builtin.lineinfile:
    path: /etc/environment
    regexp: '^JAVA_HOME='
    line: 'JAVA_HOME={{ java_home }}'
    create: true
    mode: "0644"

- name: Verify Java installation
  ansible.builtin.command:
    cmd: "{{ java_home }}/bin/java -version"
  register: java_version_output
  changed_when: false

- name: Display Java version
  ansible.builtin.debug:
    var: java_version_output.stderr_lines
```

**Step 2: Lint the role**

Run: `uv run ansible-lint roles/java`
Expected: No errors

**Step 3: Commit**

```bash
git add roles/java/tasks/main.yml
git commit -m "feat(java): implement OpenJDK installation tasks"
```

---

## Task 6: Java Role - Molecule Test Setup

**Files:**
- Create: `roles/java/molecule/default/molecule.yml`
- Create: `roles/java/molecule/default/converge.yml`
- Create: `roles/java/molecule/default/verify.yml`

**Step 1: Create molecule directory**

Run: `mkdir -p roles/java/molecule/default`

**Step 2: Create molecule.yml**

```yaml
---
dependency:
  name: galaxy

driver:
  name: podman

platforms:
  - name: java-test
    image: ubuntu:24.04
    privileged: true
    command: /sbin/init
    systemd: true

provisioner:
  name: ansible

verifier:
  name: ansible
```

**Step 3: Create converge.yml**

```yaml
---
- name: Converge
  hosts: all
  become: true

  roles:
    - role: java
```

**Step 4: Create verify.yml**

```yaml
---
- name: Verify
  hosts: all
  become: true

  tasks:
    - name: Check Java is installed
      ansible.builtin.command:
        cmd: java -version
      register: java_check
      changed_when: false

    - name: Verify Java version is 21
      ansible.builtin.assert:
        that:
          - "'21' in java_check.stderr"
        fail_msg: "Java 21 is not installed"
        success_msg: "Java 21 is installed correctly"

    - name: Check JAVA_HOME is set
      ansible.builtin.command:
        cmd: grep JAVA_HOME /etc/environment
      register: java_home_check
      changed_when: false

    - name: Verify JAVA_HOME value
      ansible.builtin.assert:
        that:
          - "'/usr/lib/jvm/java-21-openjdk-amd64' in java_home_check.stdout"
        fail_msg: "JAVA_HOME is not set correctly"
        success_msg: "JAVA_HOME is configured correctly"
```

**Step 5: Run molecule test**

Run: `cd roles/java && uv run molecule test && cd ../..`
Expected: All tests pass (create, converge, verify, destroy)

**Step 6: Commit**

```bash
git add roles/java/molecule
git commit -m "test(java): add Molecule test for Java role"
```

---

## Task 7: Kafka Role - Structure and Variables

**Files:**
- Create: `roles/kafka/defaults/main.yml`
- Create: `roles/kafka/vars/main.yml`
- Create: `roles/kafka/meta/main.yml`
- Create: `roles/kafka/handlers/main.yml`
- Create: `roles/kafka/tasks/main.yml`

**Step 1: Create role directory structure**

Run: `mkdir -p roles/kafka/{tasks,defaults,vars,handlers,meta,templates,files}`

**Step 2: Create defaults/main.yml**

```yaml
---
# Kafka version
kafka_version: "4.1.1"
kafka_scala_version: "2.13"
kafka_download_url: "https://downloads.apache.org/kafka/{{ kafka_version }}/kafka_{{ kafka_scala_version }}-{{ kafka_version }}.tgz"
kafka_checksum_url: "{{ kafka_download_url }}.sha512"

# Directories
kafka_install_dir: "/opt/kafka"
kafka_data_dir: "/data/kafka"
kafka_log_dir: "/var/log/kafka"
kafka_config_dir: "/etc/kafka"

# User/Group
kafka_user: "kafka"
kafka_group: "kafka"

# KRaft settings
kafka_cluster_id: ""
kafka_combined_mode: true
kafka_node_id: 1
kafka_quorum_voters: ""

# Network
kafka_port: 9092
kafka_controller_port: 9093

# Retention (3 days default)
kafka_log_retention_hours: 72
kafka_log_retention_bytes: 53687091200

# Performance - resource aware defaults
kafka_heap_size: "{{ [(ansible_memtotal_mb * 0.25) | int, 1024] | max | min(8192) }}m"
kafka_num_network_threads: "{{ [(ansible_processor_vcpus | default(2) / 2) | int, 3] | max }}"
kafka_num_io_threads: "{{ [(ansible_processor_vcpus | default(2) * 2) | int, 8] | max }}"
kafka_num_partitions: 6

# Small message optimizations (2KB messages)
kafka_message_max_bytes: 1048576
kafka_replica_fetch_max_bytes: 1048576
kafka_log_segment_bytes: 536870912

# Batch consumer friendly
kafka_fetch_min_bytes: 131072
kafka_fetch_max_wait_ms: 1000

# JMX settings (placeholder for jmx_exporter role)
kafka_jmx_opts: ""
```

**Step 3: Create vars/main.yml**

```yaml
---
# Internal variables - do not override
kafka_versioned_dir: "/opt/kafka-{{ kafka_version }}"
kafka_tarball: "kafka_{{ kafka_scala_version }}-{{ kafka_version }}.tgz"
kafka_download_dest: "/tmp/{{ kafka_tarball }}"
```

**Step 4: Create meta/main.yml**

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
  - role: java
```

**Step 5: Create handlers/main.yml**

```yaml
---
- name: Restart kafka
  ansible.builtin.systemd:
    name: kafka
    state: restarted
    daemon_reload: true
  when: kafka_service_installed | default(false)
```

**Step 6: Create tasks/main.yml (stub)**

```yaml
---
- name: Include user tasks
  ansible.builtin.include_tasks: user.yml

- name: Include install tasks
  ansible.builtin.include_tasks: install.yml

- name: Include configure tasks
  ansible.builtin.include_tasks: configure.yml

- name: Include service tasks
  ansible.builtin.include_tasks: service.yml
```

**Step 7: Commit**

```bash
git add roles/kafka
git commit -m "feat(kafka): add role structure and variables"
```

---

## Task 8: Kafka Role - User and Install Tasks

**Files:**
- Create: `roles/kafka/tasks/user.yml`
- Create: `roles/kafka/tasks/install.yml`

**Step 1: Create user.yml**

```yaml
---
- name: Create kafka group
  ansible.builtin.group:
    name: "{{ kafka_group }}"
    state: present
    system: true

- name: Create kafka user
  ansible.builtin.user:
    name: "{{ kafka_user }}"
    group: "{{ kafka_group }}"
    system: true
    shell: /usr/sbin/nologin
    home: "{{ kafka_install_dir }}"
    create_home: false
```

**Step 2: Create install.yml**

```yaml
---
- name: Create Kafka directories
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
    owner: "{{ kafka_user }}"
    group: "{{ kafka_group }}"
    mode: "0755"
  loop:
    - "{{ kafka_data_dir }}"
    - "{{ kafka_log_dir }}"
    - "{{ kafka_config_dir }}"

- name: Check if Kafka is already installed
  ansible.builtin.stat:
    path: "{{ kafka_versioned_dir }}/bin/kafka-server-start.sh"
  register: kafka_installed

- name: Download Kafka tarball
  ansible.builtin.get_url:
    url: "{{ kafka_download_url }}"
    dest: "{{ kafka_download_dest }}"
    mode: "0644"
  when: not kafka_installed.stat.exists

- name: Create versioned install directory
  ansible.builtin.file:
    path: "{{ kafka_versioned_dir }}"
    state: directory
    owner: "{{ kafka_user }}"
    group: "{{ kafka_group }}"
    mode: "0755"
  when: not kafka_installed.stat.exists

- name: Extract Kafka tarball
  ansible.builtin.unarchive:
    src: "{{ kafka_download_dest }}"
    dest: "{{ kafka_versioned_dir }}"
    remote_src: true
    owner: "{{ kafka_user }}"
    group: "{{ kafka_group }}"
    extra_opts:
      - --strip-components=1
  when: not kafka_installed.stat.exists

- name: Create symlink to current version
  ansible.builtin.file:
    src: "{{ kafka_versioned_dir }}"
    dest: "{{ kafka_install_dir }}"
    state: link
    owner: "{{ kafka_user }}"
    group: "{{ kafka_group }}"

- name: Clean up downloaded tarball
  ansible.builtin.file:
    path: "{{ kafka_download_dest }}"
    state: absent
```

**Step 3: Lint the role**

Run: `uv run ansible-lint roles/kafka`
Expected: No errors (warnings OK for now)

**Step 4: Commit**

```bash
git add roles/kafka/tasks/user.yml roles/kafka/tasks/install.yml
git commit -m "feat(kafka): add user and installation tasks"
```

---

## Task 9: Kafka Role - Configuration Tasks and Templates

**Files:**
- Create: `roles/kafka/tasks/configure.yml`
- Create: `roles/kafka/templates/server.properties.j2`

**Step 1: Create server.properties.j2 template**

```jinja2
# {{ ansible_managed }}
# Kafka {{ kafka_version }} KRaft Configuration

############################# Server Basics #############################
process.roles=broker,controller
node.id={{ kafka_node_id }}
controller.quorum.voters={{ kafka_quorum_voters }}
controller.listener.names=CONTROLLER

############################# Socket Server Settings #############################
listeners=PLAINTEXT://:{{ kafka_port }},CONTROLLER://:{{ kafka_controller_port }}
advertised.listeners=PLAINTEXT://{{ ansible_default_ipv4.address | default(ansible_host) }}:{{ kafka_port }}
inter.broker.listener.name=PLAINTEXT
listener.security.protocol.map=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT

############################# Log Basics #############################
log.dirs={{ kafka_data_dir }}
num.partitions={{ kafka_num_partitions }}
default.replication.factor=3
min.insync.replicas=2

############################# Log Retention Policy #############################
log.retention.hours={{ kafka_log_retention_hours }}
log.retention.bytes={{ kafka_log_retention_bytes }}
log.segment.bytes={{ kafka_log_segment_bytes }}
log.retention.check.interval.ms=300000

############################# Thread Configuration #############################
num.network.threads={{ kafka_num_network_threads }}
num.io.threads={{ kafka_num_io_threads }}
num.recovery.threads.per.data.dir=1

############################# Message Settings #############################
message.max.bytes={{ kafka_message_max_bytes }}
replica.fetch.max.bytes={{ kafka_replica_fetch_max_bytes }}
fetch.min.bytes={{ kafka_fetch_min_bytes }}
fetch.max.wait.ms={{ kafka_fetch_max_wait_ms }}

############################# Internal Topic Settings #############################
offsets.topic.replication.factor=3
transaction.state.log.replication.factor=3
transaction.state.log.min.isr=2

############################# Group Coordinator Settings #############################
group.initial.rebalance.delay.ms=3000
```

**Step 2: Create configure.yml**

```yaml
---
- name: Generate cluster ID on first node
  when:
    - kafka_cluster_id == ""
    - kafka_node_id == 1
  block:
    - name: Check for existing cluster ID file
      ansible.builtin.stat:
        path: "{{ kafka_config_dir }}/cluster_id"
      register: cluster_id_file

    - name: Generate new cluster ID
      ansible.builtin.command:
        cmd: "{{ kafka_install_dir }}/bin/kafka-storage.sh random-uuid"
      register: generated_cluster_id
      when: not cluster_id_file.stat.exists
      changed_when: true

    - name: Save cluster ID to file
      ansible.builtin.copy:
        content: "{{ generated_cluster_id.stdout }}"
        dest: "{{ kafka_config_dir }}/cluster_id"
        owner: "{{ kafka_user }}"
        group: "{{ kafka_group }}"
        mode: "0644"
      when: not cluster_id_file.stat.exists

- name: Read cluster ID from first node
  ansible.builtin.slurp:
    src: "{{ kafka_config_dir }}/cluster_id"
  register: cluster_id_content
  delegate_to: "{{ groups['kafka'][0] }}"
  run_once: true

- name: Set cluster ID fact
  ansible.builtin.set_fact:
    kafka_actual_cluster_id: "{{ kafka_cluster_id if kafka_cluster_id != '' else (cluster_id_content.content | b64decode | trim) }}"

- name: Deploy server.properties
  ansible.builtin.template:
    src: server.properties.j2
    dest: "{{ kafka_config_dir }}/server.properties"
    owner: "{{ kafka_user }}"
    group: "{{ kafka_group }}"
    mode: "0644"
  notify: Restart kafka

- name: Check if storage is formatted
  ansible.builtin.stat:
    path: "{{ kafka_data_dir }}/meta.properties"
  register: kafka_storage_formatted

- name: Format storage directory
  ansible.builtin.command:
    cmd: >
      {{ kafka_install_dir }}/bin/kafka-storage.sh format
      --config {{ kafka_config_dir }}/server.properties
      --cluster-id {{ kafka_actual_cluster_id }}
      --ignore-formatted
  become: true
  become_user: "{{ kafka_user }}"
  when: not kafka_storage_formatted.stat.exists
  changed_when: true
```

**Step 3: Commit**

```bash
git add roles/kafka/tasks/configure.yml roles/kafka/templates/server.properties.j2
git commit -m "feat(kafka): add configuration tasks and server.properties template"
```

---

## Task 10: Kafka Role - Service Tasks and Template

**Files:**
- Create: `roles/kafka/tasks/service.yml`
- Create: `roles/kafka/templates/kafka.service.j2`

**Step 1: Create kafka.service.j2 template**

```jinja2
# {{ ansible_managed }}
[Unit]
Description=Apache Kafka Server
Documentation=https://kafka.apache.org/documentation/
After=network.target

[Service]
Type=simple
User={{ kafka_user }}
Group={{ kafka_group }}

Environment="JAVA_HOME={{ java_home | default('/usr/lib/jvm/java-21-openjdk-amd64') }}"
Environment="KAFKA_HEAP_OPTS=-Xms{{ kafka_heap_size }} -Xmx{{ kafka_heap_size }}"
Environment="KAFKA_JVM_PERFORMANCE_OPTS=-server -XX:+UseG1GC -XX:MaxGCPauseMillis=20 -XX:InitiatingHeapOccupancyPercent=35 -XX:+ExplicitGCInvokesConcurrent -XX:+ParallelRefProcEnabled"
{% if kafka_jmx_opts != "" %}
Environment="KAFKA_OPTS={{ kafka_jmx_opts }}"
{% endif %}

ExecStart={{ kafka_install_dir }}/bin/kafka-server-start.sh {{ kafka_config_dir }}/server.properties
ExecStop={{ kafka_install_dir }}/bin/kafka-server-stop.sh

Restart=on-failure
RestartSec=10

LimitNOFILE=100000
LimitNPROC=32768

StandardOutput=append:{{ kafka_log_dir }}/kafka.log
StandardError=append:{{ kafka_log_dir }}/kafka-error.log

[Install]
WantedBy=multi-user.target
```

**Step 2: Create service.yml**

```yaml
---
- name: Deploy Kafka systemd service
  ansible.builtin.template:
    src: kafka.service.j2
    dest: /etc/systemd/system/kafka.service
    owner: root
    group: root
    mode: "0644"
  notify: Restart kafka
  register: kafka_service_file

- name: Set kafka service installed fact
  ansible.builtin.set_fact:
    kafka_service_installed: true

- name: Reload systemd daemon
  ansible.builtin.systemd:
    daemon_reload: true
  when: kafka_service_file.changed

- name: Enable and start Kafka service
  ansible.builtin.systemd:
    name: kafka
    enabled: true
    state: started
```

**Step 3: Lint the role**

Run: `uv run ansible-lint roles/kafka`
Expected: No errors

**Step 4: Commit**

```bash
git add roles/kafka/tasks/service.yml roles/kafka/templates/kafka.service.j2
git commit -m "feat(kafka): add systemd service tasks and template"
```

---

## Task 11: Kafka Role - Molecule Test

**Files:**
- Create: `roles/kafka/molecule/default/molecule.yml`
- Create: `roles/kafka/molecule/default/converge.yml`
- Create: `roles/kafka/molecule/default/verify.yml`
- Create: `roles/kafka/molecule/default/prepare.yml`

**Step 1: Create molecule directory**

Run: `mkdir -p roles/kafka/molecule/default`

**Step 2: Create molecule.yml**

```yaml
---
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

**Step 3: Create prepare.yml**

```yaml
---
- name: Prepare
  hosts: all
  become: true

  tasks:
    - name: Create /data directory for Kafka
      ansible.builtin.file:
        path: /data
        state: directory
        mode: "0755"
```

**Step 4: Create converge.yml**

```yaml
---
- name: Converge
  hosts: kafka
  become: true

  roles:
    - role: java
    - role: kafka
```

**Step 5: Create verify.yml**

```yaml
---
- name: Verify
  hosts: kafka
  become: true

  tasks:
    - name: Check Kafka service is running
      ansible.builtin.systemd:
        name: kafka
      register: kafka_service
      failed_when: kafka_service.status.ActiveState != "active"

    - name: Wait for Kafka port to be available
      ansible.builtin.wait_for:
        port: 9092
        timeout: 60

    - name: Wait for controller port to be available
      ansible.builtin.wait_for:
        port: 9093
        timeout: 60

    - name: Check Kafka can list topics
      ansible.builtin.command:
        cmd: /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
      register: kafka_topics
      changed_when: false
      retries: 5
      delay: 10

    - name: Verify Kafka cluster metadata
      ansible.builtin.command:
        cmd: /opt/kafka/bin/kafka-metadata.sh --snapshot /data/kafka/__cluster_metadata-0/00000000000000000000.log --command-config /etc/kafka/server.properties
      register: kafka_metadata
      changed_when: false
      failed_when: false
```

**Step 6: Run molecule test**

Run: `cd roles/kafka && uv run molecule test && cd ../..`
Expected: All tests pass

**Step 7: Commit**

```bash
git add roles/kafka/molecule
git commit -m "test(kafka): add Molecule test for Kafka role"
```

---

## Task 12: JMX Exporter Role - Structure and Implementation

**Files:**
- Create: `roles/jmx_exporter/defaults/main.yml`
- Create: `roles/jmx_exporter/tasks/main.yml`
- Create: `roles/jmx_exporter/meta/main.yml`
- Create: `roles/jmx_exporter/templates/kafka-jmx-config.yml.j2`

**Step 1: Create role directory structure**

Run: `mkdir -p roles/jmx_exporter/{tasks,defaults,meta,templates}`

**Step 2: Create defaults/main.yml**

```yaml
---
jmx_exporter_version: "1.1.0"
jmx_exporter_port: 7071
jmx_exporter_install_dir: "/opt/jmx_exporter"
jmx_exporter_config_file: "{{ kafka_config_dir | default('/etc/kafka') }}/jmx-exporter.yml"
jmx_exporter_jar: "jmx_prometheus_javaagent-{{ jmx_exporter_version }}.jar"
jmx_exporter_download_url: "https://repo1.maven.org/maven2/io/prometheus/jmx/jmx_prometheus_javaagent/{{ jmx_exporter_version }}/{{ jmx_exporter_jar }}"
```

**Step 3: Create meta/main.yml**

```yaml
---
galaxy_info:
  author: your_name
  description: Install JMX Exporter for Kafka metrics
  license: MIT
  min_ansible_version: "2.16"
  platforms:
    - name: Ubuntu
      versions:
        - noble

dependencies: []
```

**Step 4: Create kafka-jmx-config.yml.j2 template**

```jinja2
# {{ ansible_managed }}
# JMX Exporter configuration for Kafka
---
startDelaySeconds: 0
lowercaseOutputName: true
lowercaseOutputLabelNames: true

rules:
  # Kafka broker metrics
  - pattern: kafka.server<type=(.+), name=(.+), clientId=(.+), topic=(.+), partition=(.*)><>Value
    name: kafka_server_$1_$2
    type: GAUGE
    labels:
      clientId: "$3"
      topic: "$4"
      partition: "$5"

  - pattern: kafka.server<type=(.+), name=(.+), clientId=(.+), brokerHost=(.+), brokerPort=(.+)><>Value
    name: kafka_server_$1_$2
    type: GAUGE
    labels:
      clientId: "$3"
      broker: "$4:$5"

  - pattern: kafka.server<type=(.+), name=(.+)><>Value
    name: kafka_server_$1_$2
    type: GAUGE

  - pattern: kafka.server<type=(.+), name=(.+)><>Count
    name: kafka_server_$1_$2_total
    type: COUNTER

  # Kafka controller metrics
  - pattern: kafka.controller<type=(.+), name=(.+)><>Value
    name: kafka_controller_$1_$2
    type: GAUGE

  - pattern: kafka.controller<type=(.+), name=(.+)><>Count
    name: kafka_controller_$1_$2_total
    type: COUNTER

  # Kafka network metrics
  - pattern: kafka.network<type=(.+), name=(.+), request=(.+), error=(.+)><>Count
    name: kafka_network_$1_$2_total
    type: COUNTER
    labels:
      request: "$3"
      error: "$4"

  - pattern: kafka.network<type=(.+), name=(.+), request=(.+)><>Count
    name: kafka_network_$1_$2_total
    type: COUNTER
    labels:
      request: "$3"

  - pattern: kafka.network<type=(.+), name=(.+)><>Value
    name: kafka_network_$1_$2
    type: GAUGE

  # Kafka log metrics
  - pattern: kafka.log<type=(.+), name=(.+), topic=(.+), partition=(.+)><>Value
    name: kafka_log_$1_$2
    type: GAUGE
    labels:
      topic: "$3"
      partition: "$4"

  # JVM metrics
  - pattern: java.lang<type=Memory><HeapMemoryUsage>(\w+)
    name: jvm_memory_heap_$1_bytes
    type: GAUGE

  - pattern: java.lang<type=Memory><NonHeapMemoryUsage>(\w+)
    name: jvm_memory_nonheap_$1_bytes
    type: GAUGE

  - pattern: java.lang<type=GarbageCollector, name=(.+)><>CollectionCount
    name: jvm_gc_collection_count_total
    type: COUNTER
    labels:
      gc: "$1"

  - pattern: java.lang<type=GarbageCollector, name=(.+)><>CollectionTime
    name: jvm_gc_collection_time_seconds_total
    type: COUNTER
    labels:
      gc: "$1"
    valueFactor: 0.001

  - pattern: java.lang<type=Threading><>ThreadCount
    name: jvm_threads_current
    type: GAUGE
```

**Step 5: Create tasks/main.yml**

```yaml
---
- name: Create JMX exporter install directory
  ansible.builtin.file:
    path: "{{ jmx_exporter_install_dir }}"
    state: directory
    owner: "{{ kafka_user | default('kafka') }}"
    group: "{{ kafka_group | default('kafka') }}"
    mode: "0755"

- name: Download JMX exporter jar
  ansible.builtin.get_url:
    url: "{{ jmx_exporter_download_url }}"
    dest: "{{ jmx_exporter_install_dir }}/{{ jmx_exporter_jar }}"
    owner: "{{ kafka_user | default('kafka') }}"
    group: "{{ kafka_group | default('kafka') }}"
    mode: "0644"

- name: Deploy JMX exporter configuration
  ansible.builtin.template:
    src: kafka-jmx-config.yml.j2
    dest: "{{ jmx_exporter_config_file }}"
    owner: "{{ kafka_user | default('kafka') }}"
    group: "{{ kafka_group | default('kafka') }}"
    mode: "0644"
  notify: Restart kafka

- name: Set JMX exporter Java agent options fact
  ansible.builtin.set_fact:
    kafka_jmx_opts: "-javaagent:{{ jmx_exporter_install_dir }}/{{ jmx_exporter_jar }}={{ jmx_exporter_port }}:{{ jmx_exporter_config_file }}"

- name: Update Kafka systemd service with JMX options
  ansible.builtin.lineinfile:
    path: /etc/systemd/system/kafka.service
    regexp: '^Environment="KAFKA_OPTS='
    line: 'Environment="KAFKA_OPTS={{ kafka_jmx_opts }}"'
    insertafter: '^Environment="KAFKA_JVM_PERFORMANCE_OPTS='
  notify: Restart kafka
```

**Step 6: Create handlers/main.yml**

Run: `mkdir -p roles/jmx_exporter/handlers`

```yaml
---
- name: Restart kafka
  ansible.builtin.systemd:
    name: kafka
    state: restarted
    daemon_reload: true
```

**Step 7: Commit**

```bash
git add roles/jmx_exporter
git commit -m "feat(jmx_exporter): add JMX exporter role for Kafka metrics"
```

---

## Task 13: Kafka Exporter Role - Structure and Implementation

**Files:**
- Create: `roles/kafka_exporter/defaults/main.yml`
- Create: `roles/kafka_exporter/tasks/main.yml`
- Create: `roles/kafka_exporter/meta/main.yml`
- Create: `roles/kafka_exporter/handlers/main.yml`
- Create: `roles/kafka_exporter/templates/kafka-exporter.service.j2`

**Step 1: Create role directory structure**

Run: `mkdir -p roles/kafka_exporter/{tasks,defaults,meta,handlers,templates}`

**Step 2: Create defaults/main.yml**

```yaml
---
kafka_exporter_version: "1.8.0"
kafka_exporter_port: 9308
kafka_exporter_install_dir: "/opt/kafka_exporter"
kafka_exporter_user: "{{ kafka_user | default('kafka') }}"
kafka_exporter_group: "{{ kafka_group | default('kafka') }}"
kafka_exporter_download_url: "https://github.com/danielqsj/kafka_exporter/releases/download/v{{ kafka_exporter_version }}/kafka_exporter-{{ kafka_exporter_version }}.linux-amd64.tar.gz"
kafka_exporter_kafka_server: "localhost:9092"
kafka_exporter_extra_args: ""
```

**Step 3: Create meta/main.yml**

```yaml
---
galaxy_info:
  author: your_name
  description: Install Kafka Exporter for Prometheus metrics
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
- name: Restart kafka_exporter
  ansible.builtin.systemd:
    name: kafka_exporter
    state: restarted
    daemon_reload: true
```

**Step 5: Create kafka-exporter.service.j2 template**

```jinja2
# {{ ansible_managed }}
[Unit]
Description=Kafka Exporter for Prometheus
Documentation=https://github.com/danielqsj/kafka_exporter
After=network.target kafka.service

[Service]
Type=simple
User={{ kafka_exporter_user }}
Group={{ kafka_exporter_group }}

ExecStart={{ kafka_exporter_install_dir }}/kafka_exporter \
  --kafka.server={{ kafka_exporter_kafka_server }} \
  --web.listen-address=:{{ kafka_exporter_port }} \
  {{ kafka_exporter_extra_args }}

Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Step 6: Create tasks/main.yml**

```yaml
---
- name: Create Kafka exporter install directory
  ansible.builtin.file:
    path: "{{ kafka_exporter_install_dir }}"
    state: directory
    owner: "{{ kafka_exporter_user }}"
    group: "{{ kafka_exporter_group }}"
    mode: "0755"

- name: Check if Kafka exporter is already installed
  ansible.builtin.stat:
    path: "{{ kafka_exporter_install_dir }}/kafka_exporter"
  register: kafka_exporter_installed

- name: Download Kafka exporter
  ansible.builtin.get_url:
    url: "{{ kafka_exporter_download_url }}"
    dest: "/tmp/kafka_exporter.tar.gz"
    mode: "0644"
  when: not kafka_exporter_installed.stat.exists

- name: Extract Kafka exporter
  ansible.builtin.unarchive:
    src: "/tmp/kafka_exporter.tar.gz"
    dest: "{{ kafka_exporter_install_dir }}"
    remote_src: true
    owner: "{{ kafka_exporter_user }}"
    group: "{{ kafka_exporter_group }}"
    extra_opts:
      - --strip-components=1
  when: not kafka_exporter_installed.stat.exists

- name: Clean up downloaded tarball
  ansible.builtin.file:
    path: "/tmp/kafka_exporter.tar.gz"
    state: absent

- name: Deploy Kafka exporter systemd service
  ansible.builtin.template:
    src: kafka-exporter.service.j2
    dest: /etc/systemd/system/kafka_exporter.service
    owner: root
    group: root
    mode: "0644"
  notify: Restart kafka_exporter

- name: Enable and start Kafka exporter service
  ansible.builtin.systemd:
    name: kafka_exporter
    enabled: true
    state: started
    daemon_reload: true
```

**Step 7: Commit**

```bash
git add roles/kafka_exporter
git commit -m "feat(kafka_exporter): add Kafka exporter role for consumer lag metrics"
```

---

## Task 14: JMX Exporter and Kafka Exporter - Molecule Tests

**Files:**
- Create: `roles/jmx_exporter/molecule/default/molecule.yml`
- Create: `roles/jmx_exporter/molecule/default/converge.yml`
- Create: `roles/jmx_exporter/molecule/default/verify.yml`
- Create: `roles/kafka_exporter/molecule/default/molecule.yml`
- Create: `roles/kafka_exporter/molecule/default/converge.yml`
- Create: `roles/kafka_exporter/molecule/default/verify.yml`

**Step 1: Create JMX exporter molecule directory**

Run: `mkdir -p roles/jmx_exporter/molecule/default`

**Step 2: Create JMX exporter molecule.yml**

```yaml
---
dependency:
  name: galaxy

driver:
  name: podman

platforms:
  - name: jmx-test
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
        kafka_quorum_voters: "1@jmx-test:9093"
    host_vars:
      jmx-test:
        kafka_node_id: 1

verifier:
  name: ansible
```

**Step 3: Create JMX exporter converge.yml**

```yaml
---
- name: Converge
  hosts: all
  become: true

  pre_tasks:
    - name: Create /data directory
      ansible.builtin.file:
        path: /data
        state: directory
        mode: "0755"

  roles:
    - role: java
    - role: kafka
    - role: jmx_exporter
```

**Step 4: Create JMX exporter verify.yml**

```yaml
---
- name: Verify
  hosts: all
  become: true

  tasks:
    - name: Wait for JMX exporter port
      ansible.builtin.wait_for:
        port: 7071
        timeout: 60

    - name: Check JMX exporter metrics endpoint
      ansible.builtin.uri:
        url: http://localhost:7071/metrics
        return_content: true
      register: jmx_metrics
      retries: 5
      delay: 10

    - name: Verify JMX metrics contain Kafka data
      ansible.builtin.assert:
        that:
          - "'jvm_memory_heap' in jmx_metrics.content"
        fail_msg: "JMX exporter is not returning expected metrics"
        success_msg: "JMX exporter is working correctly"
```

**Step 5: Create Kafka exporter molecule directory**

Run: `mkdir -p roles/kafka_exporter/molecule/default`

**Step 6: Create Kafka exporter molecule.yml**

```yaml
---
dependency:
  name: galaxy

driver:
  name: podman

platforms:
  - name: kafka-exp-test
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
        kafka_quorum_voters: "1@kafka-exp-test:9093"
    host_vars:
      kafka-exp-test:
        kafka_node_id: 1

verifier:
  name: ansible
```

**Step 7: Create Kafka exporter converge.yml**

```yaml
---
- name: Converge
  hosts: all
  become: true

  pre_tasks:
    - name: Create /data directory
      ansible.builtin.file:
        path: /data
        state: directory
        mode: "0755"

  roles:
    - role: java
    - role: kafka
    - role: kafka_exporter
```

**Step 8: Create Kafka exporter verify.yml**

```yaml
---
- name: Verify
  hosts: all
  become: true

  tasks:
    - name: Check Kafka exporter service is running
      ansible.builtin.systemd:
        name: kafka_exporter
      register: kafka_exporter_service
      failed_when: kafka_exporter_service.status.ActiveState != "active"

    - name: Wait for Kafka exporter port
      ansible.builtin.wait_for:
        port: 9308
        timeout: 60

    - name: Check Kafka exporter metrics endpoint
      ansible.builtin.uri:
        url: http://localhost:9308/metrics
        return_content: true
      register: kafka_exp_metrics
      retries: 5
      delay: 10

    - name: Verify Kafka exporter metrics
      ansible.builtin.assert:
        that:
          - "'kafka_brokers' in kafka_exp_metrics.content"
        fail_msg: "Kafka exporter is not returning expected metrics"
        success_msg: "Kafka exporter is working correctly"
```

**Step 9: Commit**

```bash
git add roles/jmx_exporter/molecule roles/kafka_exporter/molecule
git commit -m "test: add Molecule tests for JMX and Kafka exporter roles"
```

---

## Task 15: Main Playbook and Inventory

**Files:**
- Create: `playbooks/kafka.yml`
- Create: `inventories/production/hosts.yml`
- Create: `inventories/production/group_vars/kafka.yml`

**Step 1: Create main playbook**

```yaml
---
- name: Setup Kafka Cluster
  hosts: kafka
  become: true

  pre_tasks:
    - name: Gather hardware and network facts
      ansible.builtin.setup:
        gather_subset:
          - hardware
          - network

    - name: Display target node info
      ansible.builtin.debug:
        msg: "Setting up Kafka node {{ kafka_node_id }} on {{ ansible_hostname }} ({{ ansible_default_ipv4.address | default('unknown') }})"

  roles:
    - role: java
      tags: [java]

    - role: kafka
      tags: [kafka]

    - role: jmx_exporter
      tags: [jmx, monitoring]

    - role: kafka_exporter
      tags: [kafka_exporter, monitoring]

  post_tasks:
    - name: Display Kafka cluster status
      ansible.builtin.debug:
        msg:
          - "Kafka node {{ kafka_node_id }} setup complete"
          - "Broker: {{ ansible_default_ipv4.address | default(ansible_host) }}:{{ kafka_port }}"
          - "JMX metrics: http://{{ ansible_default_ipv4.address | default(ansible_host) }}:{{ jmx_exporter_port }}/metrics"
          - "Kafka metrics: http://{{ ansible_default_ipv4.address | default(ansible_host) }}:{{ kafka_exporter_port }}/metrics"
```

**Step 2: Create production inventory hosts.yml**

```yaml
---
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

**Step 3: Create production group_vars/kafka.yml**

```yaml
---
# Override defaults for production environment

# Resource settings - adjust based on VM size
# kafka_heap_size: "6g"

# Retention settings
kafka_log_retention_hours: 72
kafka_log_retention_bytes: 53687091200

# Data directory (ensure dedicated disk is mounted here)
kafka_data_dir: "/data/kafka"

# Replication settings for 3-node cluster
kafka_default_replication_factor: 3
kafka_min_insync_replicas: 2
```

**Step 4: Lint the playbook**

Run: `uv run ansible-lint playbooks/kafka.yml`
Expected: No errors

**Step 5: Syntax check**

Run: `uv run ansible-playbook playbooks/kafka.yml --syntax-check`
Expected: "playbook: playbooks/kafka.yml" (no errors)

**Step 6: Commit**

```bash
git add playbooks inventories
git commit -m "feat: add main Kafka playbook and production inventory"
```

---

## Task 16: Final Integration Test

**Files:**
- Create: `molecule/default/molecule.yml`
- Create: `molecule/default/converge.yml`
- Create: `molecule/default/verify.yml`
- Create: `molecule/default/prepare.yml`

**Step 1: Create project-level molecule directory**

Run: `mkdir -p molecule/default`

**Step 2: Create molecule.yml**

```yaml
---
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
  playbooks:
    converge: converge.yml
    prepare: prepare.yml
    verify: verify.yml
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

scenario:
  name: default
  test_sequence:
    - destroy
    - create
    - prepare
    - converge
    - verify
    - destroy
```

**Step 3: Create prepare.yml**

```yaml
---
- name: Prepare
  hosts: all
  become: true

  tasks:
    - name: Create /data directory for Kafka
      ansible.builtin.file:
        path: /data
        state: directory
        mode: "0755"
```

**Step 4: Create converge.yml**

```yaml
---
- name: Converge
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
    - role: kafka
    - role: jmx_exporter
    - role: kafka_exporter
```

**Step 5: Create verify.yml**

```yaml
---
- name: Verify Kafka Cluster
  hosts: kafka
  become: true

  tasks:
    - name: Verify Kafka service is running
      ansible.builtin.systemd:
        name: kafka
      register: kafka_service
      failed_when: kafka_service.status.ActiveState != "active"

    - name: Wait for Kafka broker port
      ansible.builtin.wait_for:
        port: 9092
        timeout: 120

    - name: Wait for Kafka controller port
      ansible.builtin.wait_for:
        port: 9093
        timeout: 120

    - name: Wait for JMX exporter port
      ansible.builtin.wait_for:
        port: 7071
        timeout: 60

    - name: Wait for Kafka exporter port
      ansible.builtin.wait_for:
        port: 9308
        timeout: 60

- name: Verify Kafka Cluster Functionality
  hosts: kafka-1
  become: true

  tasks:
    - name: Create test topic
      ansible.builtin.command:
        cmd: >
          /opt/kafka/bin/kafka-topics.sh
          --bootstrap-server localhost:9092
          --create
          --topic test-topic
          --partitions 3
          --replication-factor 3
          --if-not-exists
      register: create_topic
      changed_when: "'Created topic' in create_topic.stdout"
      retries: 5
      delay: 10

    - name: List topics
      ansible.builtin.command:
        cmd: /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
      register: topic_list
      changed_when: false

    - name: Verify test topic exists
      ansible.builtin.assert:
        that:
          - "'test-topic' in topic_list.stdout"
        fail_msg: "Test topic was not created"
        success_msg: "Kafka cluster is functional - test topic created successfully"

    - name: Describe test topic
      ansible.builtin.command:
        cmd: /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic test-topic
      register: topic_desc
      changed_when: false

    - name: Verify topic replication
      ansible.builtin.assert:
        that:
          - "'ReplicationFactor: 3' in topic_desc.stdout"
        fail_msg: "Topic replication factor is not 3"
        success_msg: "Topic replication is configured correctly"

    - name: Check JMX metrics endpoint
      ansible.builtin.uri:
        url: http://localhost:7071/metrics
        return_content: true
      register: jmx_metrics

    - name: Check Kafka exporter metrics endpoint
      ansible.builtin.uri:
        url: http://localhost:9308/metrics
        return_content: true
      register: kafka_metrics

    - name: Final verification summary
      ansible.builtin.debug:
        msg:
          - "=== Kafka Cluster Verification Complete ==="
          - "All 3 nodes are running"
          - "Broker ports (9092) - OK"
          - "Controller ports (9093) - OK"
          - "JMX exporter (7071) - OK"
          - "Kafka exporter (9308) - OK"
          - "Test topic with replication factor 3 - OK"
```

**Step 6: Run full integration test**

Run: `uv run molecule test`
Expected: All tests pass

**Step 7: Commit**

```bash
git add molecule
git commit -m "test: add full cluster integration test with Molecule"
```

---

## Task 17: Documentation - README

**Files:**
- Create: `README.md`

**Step 1: Create README.md**

```markdown
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
- Podman (for testing)
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

## Testing

```bash
# Test individual role
cd roles/java && uv run molecule test

# Test full cluster
uv run molecule test
```

## VM Sizing

| Profile | vCPU | RAM | Disk | Capacity |
|---------|------|-----|------|----------|
| Starting | 4 | 8GB | 1TB | ~3K msg/s |
| Recommended | 8 | 16GB | 1TB | ~7K msg/s |
| Full | 16 | 32GB | 2TB | 10K+ msg/s |

## License

MIT
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add project README"
```

---

## Summary

| Task | Description |
|------|-------------|
| 1 | Project setup - Python environment with uv |
| 2 | Project setup - Ansible configuration |
| 3 | Project setup - Directory structure |
| 4 | Java role - Structure and variables |
| 5 | Java role - Implementation |
| 6 | Java role - Molecule test |
| 7 | Kafka role - Structure and variables |
| 8 | Kafka role - User and install tasks |
| 9 | Kafka role - Configuration and templates |
| 10 | Kafka role - Service tasks |
| 11 | Kafka role - Molecule test |
| 12 | JMX Exporter role - Full implementation |
| 13 | Kafka Exporter role - Full implementation |
| 14 | Exporter roles - Molecule tests |
| 15 | Main playbook and inventory |
| 16 | Full integration test |
| 17 | Documentation |
