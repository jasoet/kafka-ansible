# Grafana Monitoring Stack Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy a self-hosted monitoring stack (Grafana, VictoriaMetrics, Loki, Alloy) on a dedicated VM using Podman Quadlet, with Alloy agents on each Kafka node for metric scraping and log shipping.

**Architecture:** Monitoring VM runs 4 containers (Grafana, VictoriaMetrics, Loki, Alloy) managed by Podman Quadlet via systemd. Each Kafka node runs Alloy as a systemd service to scrape local exporters and ship Kafka logs. A `compose.yaml` serves as the source of truth, converted to Quadlet files using `podlets`.

**Tech Stack:** Ansible, Podman Quadlet, Grafana, VictoriaMetrics, Grafana Loki, Grafana Alloy, podlets, Vagrant (testing)

**Design doc:** `docs/plans/2026-02-09-grafana-monitoring-stack-design.md`

---

### Task 1: Create monitoring/compose.yaml

The container stack source of truth.

**Files:**
- Create: `monitoring/compose.yaml`

**Step 1: Create compose.yaml**

```yaml
# Monitoring Stack - Source of Truth
# Convert to Quadlet: podlets compose monitoring/compose.yaml
name: monitoring

networks:
  monitoring:
    driver: bridge

volumes:
  victoriametrics-data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/monitoring/victoriametrics
  loki-data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/monitoring/loki
  grafana-data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/monitoring/grafana

services:
  victoriametrics:
    image: docker.io/victoriametrics/victoria-metrics:v1.113.0
    container_name: victoriametrics
    ports:
      - "8428:8428"
    volumes:
      - victoriametrics-data:/storage
    command:
      - "-storageDataPath=/storage"
      - "-retentionPeriod=30d"
      - "-httpListenAddr=:8428"
    networks:
      - monitoring
    restart: unless-stopped

  loki:
    image: docker.io/grafana/loki:3.4.2
    container_name: loki
    ports:
      - "3100:3100"
    volumes:
      - loki-data:/loki
      - ./loki/config.yaml:/etc/loki/config.yaml:ro
    command:
      - "-config.file=/etc/loki/config.yaml"
    networks:
      - monitoring
    restart: unless-stopped

  grafana:
    image: docker.io/grafana/grafana:11.5.2
    container_name: grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    networks:
      - monitoring
    restart: unless-stopped

  alloy:
    image: docker.io/grafana/alloy:v1.6.1
    container_name: alloy
    ports:
      - "12345:12345"
    volumes:
      - ./alloy/config.alloy:/etc/alloy/config.alloy:ro
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
    command:
      - "run"
      - "/etc/alloy/config.alloy"
      - "--storage.path=/var/lib/alloy/data"
    networks:
      - monitoring
    restart: unless-stopped
    pid: host
```

**Step 2: Commit**

```bash
git add monitoring/compose.yaml
git commit -m "feat(monitoring): add compose.yaml for monitoring stack"
```

---

### Task 2: Create Loki configuration

**Files:**
- Create: `monitoring/loki/config.yaml`

**Step 1: Create Loki config**

```yaml
auth_enabled: false

server:
  http_listen_port: 3100

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: "2024-01-01"
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  retention_period: 720h  # 30 days

compactor:
  working_directory: /loki/compactor
  compaction_interval: 10m
  retention_enabled: true
  retention_delete_delay: 2h
  delete_request_store: filesystem
```

**Step 2: Commit**

```bash
git add monitoring/loki/config.yaml
git commit -m "feat(monitoring): add Loki configuration"
```

---

### Task 3: Create Alloy configuration for monitoring VM

**Files:**
- Create: `monitoring/alloy/config.alloy`

**Step 1: Create Alloy config for monitoring VM self-monitoring**

```alloy
// ============================================
// Alloy config for Monitoring VM
// Self-monitoring: scrapes VM, Loki, Grafana, VictoriaMetrics
// ============================================

// --- Node Exporter integration (built-in) ---
prometheus.exporter.unix "host" {
  procfs_path    = "/host/proc"
  sysfs_path     = "/host/sys"
}

prometheus.scrape "host_metrics" {
  targets    = prometheus.exporter.unix.host.targets
  forward_to = [prometheus.remote_write.victoriametrics.receiver]

  scrape_interval = "15s"
}

// --- Scrape monitoring stack metrics ---
prometheus.scrape "monitoring_stack" {
  targets = [
    {"__address__" = "victoriametrics:8428", "job" = "victoriametrics"},
    {"__address__" = "loki:3100",            "job" = "loki"},
    {"__address__" = "grafana:3000",         "job" = "grafana"},
  ]
  forward_to = [prometheus.remote_write.victoriametrics.receiver]

  scrape_interval = "15s"
  metrics_path    = "/metrics"
}

// --- Remote write to VictoriaMetrics ---
prometheus.remote_write "victoriametrics" {
  endpoint {
    url = "http://victoriametrics:8428/api/v1/write"
  }

  external_labels = {
    source = "monitoring-vm",
  }
}

// --- Loki log shipping ---
loki.source.journal "containers" {
  forward_to = [loki.write.loki.receiver]
  labels     = {source = "journal", host = "monitoring-vm"}
}

loki.write "loki" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
  }
}
```

**Step 2: Commit**

```bash
git add monitoring/alloy/config.alloy
git commit -m "feat(monitoring): add Alloy config for monitoring VM self-monitoring"
```

---

### Task 4: Create Grafana provisioning (datasources)

**Files:**
- Create: `monitoring/grafana/provisioning/datasources/default.yaml`

**Step 1: Create datasource provisioning**

```yaml
apiVersion: 1

datasources:
  - name: VictoriaMetrics
    type: prometheus
    access: proxy
    url: http://victoriametrics:8428
    isDefault: true
    editable: false

  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    editable: false
```

**Step 2: Commit**

```bash
git add monitoring/grafana/provisioning/datasources/default.yaml
git commit -m "feat(monitoring): add Grafana datasource provisioning"
```

---

### Task 5: Create Grafana dashboard provisioning config

**Files:**
- Create: `monitoring/grafana/provisioning/dashboards/dashboard.yaml`

**Step 1: Create dashboard provisioning loader**

```yaml
apiVersion: 1

providers:
  - name: default
    orgId: 1
    folder: Kafka
    type: file
    disableDeletion: false
    editable: true
    options:
      path: /etc/grafana/provisioning/dashboards
      foldersFromFilesStructure: false
```

**Step 2: Commit**

```bash
git add monitoring/grafana/provisioning/dashboards/dashboard.yaml
git commit -m "feat(monitoring): add Grafana dashboard provisioning config"
```

**Note:** Dashboard JSON files (kafka-overview.json, consumer-lag.json, jvm-health.json, monitoring-stack.json) will be created in Task 12 after the stack is running and can be tested.

---

### Task 6: Generate Quadlet files with podlets

**Files:**
- Create: `monitoring/quadlet/` (generated files)

**Step 1: Install podlets if not available**

```bash
# Check if podlets is installed
which podlets || cargo install podlets
```

**Step 2: Generate Quadlet files from compose.yaml**

```bash
cd monitoring
podlets compose compose.yaml
```

This generates `.container`, `.network`, and `.volume` files. Move them to `monitoring/quadlet/`.

**Step 3: Review and commit generated files**

```bash
mkdir -p monitoring/quadlet
mv *.container *.network *.volume monitoring/quadlet/ 2>/dev/null || true
git add monitoring/quadlet/
git commit -m "feat(monitoring): add Quadlet unit files generated by podlets"
```

---

### Task 7: Create the Alloy Ansible role (for Kafka nodes)

**Files:**
- Create: `roles/alloy/defaults/main.yml`
- Create: `roles/alloy/tasks/main.yml`
- Create: `roles/alloy/handlers/main.yml`
- Create: `roles/alloy/templates/config.alloy.j2`
- Create: `roles/alloy/templates/alloy.service.j2`

**Step 1: Create role defaults**

`roles/alloy/defaults/main.yml`:
```yaml
---
alloy_version: "1.6.1"
alloy_port: 12345
alloy_user: "alloy"
alloy_group: "alloy"
alloy_install_dir: "/opt/alloy"
alloy_config_dir: "/etc/alloy"
alloy_data_dir: "/var/lib/alloy"

# Architecture mapping
alloy_arch_map:
  x86_64: "amd64"
  aarch64: "arm64"

alloy_arch: "{{ alloy_arch_map[ansible_architecture] | default('amd64') }}"

alloy_download_url: >-
  https://github.com/grafana/alloy/releases/download/v{{ alloy_version }}/alloy-linux-{{ alloy_arch }}.zip

# Remote write endpoints (set via inventory group_vars)
alloy_victoriametrics_url: ""
alloy_loki_url: ""

# Scrape interval
alloy_scrape_interval: "15s"

# Kafka log path
alloy_kafka_log_path: "/opt/kafka/logs"

# Local scrape targets
alloy_scrape_targets:
  - job: "node_exporter"
    address: "localhost:9100"
  - job: "jmx_exporter"
    address: "localhost:7071"
  - job: "kafka_exporter"
    address: "localhost:9308"

# Labels added to all metrics
alloy_cluster_name: "kafka"
alloy_environment: "production"
```

**Step 2: Create tasks**

`roles/alloy/tasks/main.yml`:
```yaml
---
- name: Create alloy group
  ansible.builtin.group:
    name: "{{ alloy_group }}"
    system: true
    state: present

- name: Create alloy user
  ansible.builtin.user:
    name: "{{ alloy_user }}"
    group: "{{ alloy_group }}"
    system: true
    shell: /usr/sbin/nologin
    home: "{{ alloy_install_dir }}"
    create_home: false
    state: present

- name: Add alloy user to adm group for log access
  ansible.builtin.user:
    name: "{{ alloy_user }}"
    groups: adm
    append: true

- name: Create Alloy directories
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
    owner: "{{ alloy_user }}"
    group: "{{ alloy_group }}"
    mode: "0755"
  loop:
    - "{{ alloy_install_dir }}"
    - "{{ alloy_config_dir }}"
    - "{{ alloy_data_dir }}"

- name: Check if Alloy is already installed
  ansible.builtin.stat:
    path: "{{ alloy_install_dir }}/alloy"
  register: alloy_installed

- name: Install unzip
  ansible.builtin.apt:
    name: unzip
    state: present
    update_cache: true
    cache_valid_time: 3600
  when: not alloy_installed.stat.exists

- name: Download Alloy
  ansible.builtin.get_url:
    url: "{{ alloy_download_url }}"
    dest: "/tmp/alloy.zip"
    mode: "0644"
    timeout: 120
  register: alloy_download_result
  retries: 3
  delay: 5
  until: alloy_download_result is succeeded
  when: not alloy_installed.stat.exists

- name: Extract Alloy
  ansible.builtin.unarchive:
    src: "/tmp/alloy.zip"
    dest: "{{ alloy_install_dir }}"
    remote_src: true
    owner: "{{ alloy_user }}"
    group: "{{ alloy_group }}"
  when: not alloy_installed.stat.exists

- name: Rename Alloy binary
  ansible.builtin.copy:
    src: "{{ alloy_install_dir }}/alloy-linux-{{ alloy_arch }}"
    dest: "{{ alloy_install_dir }}/alloy"
    remote_src: true
    owner: "{{ alloy_user }}"
    group: "{{ alloy_group }}"
    mode: "0755"
  when: not alloy_installed.stat.exists

- name: Clean up downloaded archive and extracted binary
  ansible.builtin.file:
    path: "{{ item }}"
    state: absent
  loop:
    - "/tmp/alloy.zip"
    - "{{ alloy_install_dir }}/alloy-linux-{{ alloy_arch }}"

- name: Deploy Alloy configuration
  ansible.builtin.template:
    src: config.alloy.j2
    dest: "{{ alloy_config_dir }}/config.alloy"
    owner: "{{ alloy_user }}"
    group: "{{ alloy_group }}"
    mode: "0644"
  notify: Restart alloy

- name: Deploy Alloy systemd service
  ansible.builtin.template:
    src: alloy.service.j2
    dest: /etc/systemd/system/alloy.service
    owner: root
    group: root
    mode: "0644"
  notify: Restart alloy

- name: Enable and start Alloy service
  ansible.builtin.systemd:
    name: alloy
    enabled: true
    state: started
    daemon_reload: true
```

**Step 3: Create handlers**

`roles/alloy/handlers/main.yml`:
```yaml
---
- name: Restart alloy
  ansible.builtin.systemd:
    name: alloy
    state: restarted
    daemon_reload: true
```

**Step 4: Create Alloy config template for Kafka nodes**

`roles/alloy/templates/config.alloy.j2`:
```alloy
// {{ ansible_managed }}
// ============================================
// Alloy config for Kafka node: {{ inventory_hostname }}
// Scrapes local exporters + ships Kafka logs
// ============================================

// --- Scrape local exporters ---
{% for target in alloy_scrape_targets %}
prometheus.scrape "{{ target.job }}" {
  targets    = [{"__address__" = "{{ target.address }}"}]
  forward_to = [prometheus.remote_write.victoriametrics.receiver]

  scrape_interval = "{{ alloy_scrape_interval }}"
  job_name        = "{{ target.job }}"
}

{% endfor %}
// --- Remote write to VictoriaMetrics ---
prometheus.remote_write "victoriametrics" {
  endpoint {
    url = "{{ alloy_victoriametrics_url }}/api/v1/write"
  }

  external_labels = {
    cluster     = "{{ alloy_cluster_name }}",
    node        = "{{ inventory_hostname }}",
    environment = "{{ alloy_environment }}",
  }
}

// --- Kafka log collection ---
local.file_match "kafka_logs" {
  path_targets = [
    {__path__ = "{{ alloy_kafka_log_path }}/*.log", job = "kafka-logs"},
  ]
}

loki.source.file "kafka_logs" {
  targets    = local.file_match.kafka_logs.targets
  forward_to = [loki.write.loki.receiver]
}

loki.write "loki" {
  endpoint {
    url = "{{ alloy_loki_url }}/loki/api/v1/push"
  }

  external_labels = {
    cluster     = "{{ alloy_cluster_name }}",
    node        = "{{ inventory_hostname }}",
    environment = "{{ alloy_environment }}",
  }
}
```

**Step 5: Create systemd service template**

`roles/alloy/templates/alloy.service.j2`:
```ini
# {{ ansible_managed }}
[Unit]
Description=Grafana Alloy
Documentation=https://grafana.com/docs/alloy/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={{ alloy_user }}
Group={{ alloy_group }}

ExecStart={{ alloy_install_dir }}/alloy run \
    {{ alloy_config_dir }}/config.alloy \
    --storage.path={{ alloy_data_dir }}/data \
    --server.http.listen-addr=0.0.0.0:{{ alloy_port }}

Restart=on-failure
RestartSec=5

NoNewPrivileges=yes
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
```

**Step 6: Commit**

```bash
git add roles/alloy/
git commit -m "feat(monitoring): add Alloy role for Kafka node metric scraping and log shipping"
```

---

### Task 8: Add Alloy role to kafka.yml playbook

**Files:**
- Modify: `playbooks/kafka.yml`

**Step 1: Add alloy role after existing monitoring roles**

Add to the roles list in `playbooks/kafka.yml`:

```yaml
    - role: alloy
      tags: [alloy, monitoring]
```

**Step 2: Update post_tasks to include Alloy endpoint**

Add to the post_tasks debug message:

```yaml
          - "Alloy: http://{{ ansible_facts['default_ipv4']['address'] | default(ansible_host) }}:{{ alloy_port }}"
```

**Step 3: Commit**

```bash
git add playbooks/kafka.yml
git commit -m "feat(monitoring): add Alloy role to Kafka playbook"
```

---

### Task 9: Create monitoring.yml playbook

**Files:**
- Create: `playbooks/monitoring.yml`

**Step 1: Create the monitoring playbook**

```yaml
---
- name: Setup Monitoring Stack
  hosts: monitoring
  become: true

  pre_tasks:
    - name: Gather hardware and network facts
      ansible.builtin.setup:
        gather_subset:
          - hardware
          - network

    - name: Display target node info
      ansible.builtin.debug:
        msg: "Setting up monitoring on {{ ansible_facts['hostname'] }} ({{ ansible_facts['default_ipv4']['address'] | default('unknown') }})"

    - name: Install Podman
      ansible.builtin.apt:
        name:
          - podman
        state: present
        update_cache: true
        cache_valid_time: 3600

  roles:
    - role: disk_mount
      vars:
        disk_mount_path: "/data/monitoring"
        disk_mount_owner: "root"
        disk_mount_group: "root"
        disk_mount_mode: "0755"
      tags: [disk]

  tasks:
    - name: Create monitoring data directories
      ansible.builtin.file:
        path: "{{ item }}"
        state: directory
        owner: root
        group: root
        mode: "0755"
      loop:
        - /data/monitoring/victoriametrics
        - /data/monitoring/loki
        - /data/monitoring/grafana

    - name: Set Grafana data directory ownership
      ansible.builtin.file:
        path: /data/monitoring/grafana
        state: directory
        owner: "472"
        group: "472"
        mode: "0755"

    - name: Set Loki data directory ownership
      ansible.builtin.file:
        path: /data/monitoring/loki
        state: directory
        owner: "10001"
        group: "10001"
        mode: "0755"

    - name: Create Quadlet config directory
      ansible.builtin.file:
        path: /etc/containers/systemd
        state: directory
        owner: root
        group: root
        mode: "0755"

    - name: Create monitoring config directories
      ansible.builtin.file:
        path: "{{ item }}"
        state: directory
        owner: root
        group: root
        mode: "0755"
      loop:
        - /etc/monitoring
        - /etc/monitoring/alloy
        - /etc/monitoring/loki
        - /etc/monitoring/grafana
        - /etc/monitoring/grafana/provisioning
        - /etc/monitoring/grafana/provisioning/datasources
        - /etc/monitoring/grafana/provisioning/dashboards

    - name: Deploy Quadlet unit files
      ansible.builtin.copy:
        src: "{{ item }}"
        dest: /etc/containers/systemd/
        owner: root
        group: root
        mode: "0644"
      with_fileglob:
        - "../monitoring/quadlet/*"
      notify: Reload systemd

    - name: Deploy Loki configuration
      ansible.builtin.copy:
        src: "../monitoring/loki/config.yaml"
        dest: /etc/monitoring/loki/config.yaml
        owner: root
        group: root
        mode: "0644"
      notify: Restart loki

    - name: Deploy Alloy configuration
      ansible.builtin.template:
        src: "../monitoring/alloy/config.alloy"
        dest: /etc/monitoring/alloy/config.alloy
        owner: root
        group: root
        mode: "0644"
      notify: Restart alloy-container

    - name: Deploy Grafana datasource provisioning
      ansible.builtin.copy:
        src: "../monitoring/grafana/provisioning/datasources/default.yaml"
        dest: /etc/monitoring/grafana/provisioning/datasources/default.yaml
        owner: root
        group: root
        mode: "0644"
      notify: Restart grafana

    - name: Deploy Grafana dashboard provisioning
      ansible.builtin.copy:
        src: "../monitoring/grafana/provisioning/dashboards/"
        dest: /etc/monitoring/grafana/provisioning/dashboards/
        owner: root
        group: root
        mode: "0644"
      notify: Restart grafana

    - name: Reload systemd and start services
      ansible.builtin.systemd:
        daemon_reload: true

    - name: Pull container images
      ansible.builtin.command:
        cmd: "podman pull {{ item }}"
      loop:
        - docker.io/victoriametrics/victoria-metrics:v1.113.0
        - docker.io/grafana/loki:3.4.2
        - docker.io/grafana/grafana:11.5.2
        - docker.io/grafana/alloy:v1.6.1
      register: pull_result
      changed_when: "'Already exists' not in pull_result.stdout"
      retries: 3
      delay: 5
      until: pull_result is succeeded

    - name: Start Quadlet services
      ansible.builtin.systemd:
        name: "{{ item }}"
        state: started
        enabled: true
        daemon_reload: true
      loop:
        - victoriametrics
        - loki
        - grafana
        - alloy

  handlers:
    - name: Reload systemd
      ansible.builtin.systemd:
        daemon_reload: true

    - name: Restart loki
      ansible.builtin.systemd:
        name: loki
        state: restarted

    - name: Restart alloy-container
      ansible.builtin.systemd:
        name: alloy
        state: restarted

    - name: Restart grafana
      ansible.builtin.systemd:
        name: grafana
        state: restarted

  post_tasks:
    - name: Display monitoring stack status
      ansible.builtin.debug:
        msg:
          - "Monitoring stack setup complete on {{ ansible_facts['hostname'] }}"
          - "Grafana: http://{{ ansible_facts['default_ipv4']['address'] | default(ansible_host) }}:3000 (admin/admin)"
          - "VictoriaMetrics: http://{{ ansible_facts['default_ipv4']['address'] | default(ansible_host) }}:8428"
          - "Loki: http://{{ ansible_facts['default_ipv4']['address'] | default(ansible_host) }}:3100"
          - "Alloy UI: http://{{ ansible_facts['default_ipv4']['address'] | default(ansible_host) }}:12345"
```

**Step 2: Commit**

```bash
git add playbooks/monitoring.yml
git commit -m "feat(monitoring): add monitoring stack playbook with Podman Quadlet deployment"
```

---

### Task 10: Update Vagrant inventory (default: 1 Kafka + monitoring)

**Files:**
- Modify: `inventories/vagrant/hosts.yml`
- Create: `inventories/vagrant/hosts-cluster.yml`
- Create: `inventories/vagrant/group_vars/monitoring.yml`

**Step 1: Update default Vagrant inventory to single Kafka + monitoring**

`inventories/vagrant/hosts.yml`:
```yaml
---
all:
  children:
    kafka:
      hosts:
        kafka-1:
          ansible_host: 192.168.56.11
          kafka_node_id: 1
          kafka_internal_ip: 192.168.56.11
      vars:
        ansible_user: vagrant
        ansible_ssh_private_key_file: "{{ inventory_dir }}/../../tests/vagrant/.vagrant/machines/{{ inventory_hostname }}/virtualbox/private_key"
        ansible_ssh_common_args: "-o StrictHostKeyChecking=no"
        kafka_quorum_voters: "1@192.168.56.11:9093"
        kafka_default_replication_factor: 1
        kafka_min_insync_replicas: 1
        kafka_offsets_topic_replication_factor: 1
        kafka_transaction_state_log_replication_factor: 1
        alloy_victoriametrics_url: "http://192.168.56.20:8428"
        alloy_loki_url: "http://192.168.56.20:3100"
        alloy_environment: "vagrant"
    monitoring:
      hosts:
        monitoring-1:
          ansible_host: 192.168.56.20
      vars:
        ansible_user: vagrant
        ansible_ssh_private_key_file: "{{ inventory_dir }}/../../tests/vagrant/.vagrant/machines/{{ inventory_hostname }}/virtualbox/private_key"
        ansible_ssh_common_args: "-o StrictHostKeyChecking=no"
```

**Step 2: Create 3-node cluster inventory**

`inventories/vagrant/hosts-cluster.yml`:
```yaml
---
all:
  children:
    kafka:
      hosts:
        kafka-1:
          ansible_host: 192.168.56.11
          kafka_node_id: 1
          kafka_internal_ip: 192.168.56.11
        kafka-2:
          ansible_host: 192.168.56.12
          kafka_node_id: 2
          kafka_internal_ip: 192.168.56.12
        kafka-3:
          ansible_host: 192.168.56.13
          kafka_node_id: 3
          kafka_internal_ip: 192.168.56.13
      vars:
        ansible_user: vagrant
        ansible_ssh_private_key_file: "{{ inventory_dir }}/../../tests/vagrant/.vagrant/machines/{{ inventory_hostname }}/virtualbox/private_key"
        ansible_ssh_common_args: "-o StrictHostKeyChecking=no"
        kafka_quorum_voters: "1@192.168.56.11:9093,2@192.168.56.12:9093,3@192.168.56.13:9093"
        alloy_victoriametrics_url: "http://192.168.56.20:8428"
        alloy_loki_url: "http://192.168.56.20:3100"
        alloy_environment: "vagrant"
    monitoring:
      hosts:
        monitoring-1:
          ansible_host: 192.168.56.20
      vars:
        ansible_user: vagrant
        ansible_ssh_private_key_file: "{{ inventory_dir }}/../../tests/vagrant/.vagrant/machines/{{ inventory_hostname }}/virtualbox/private_key"
        ansible_ssh_common_args: "-o StrictHostKeyChecking=no"
```

**Step 3: Commit**

```bash
git add inventories/vagrant/
git commit -m "feat(monitoring): update Vagrant inventory with monitoring host and single-node default"
```

---

### Task 11: Update Vagrantfile

**Files:**
- Modify: `tests/vagrant/Vagrantfile`

**Step 1: Update Vagrantfile with configurable Kafka node count and monitoring VM**

```ruby
Vagrant.configure("2") do |config|
  config.vm.box = "bento/ubuntu-24.04"

  kafka_nodes = (ENV['KAFKA_NODES'] || 1).to_i

  (1..kafka_nodes).each do |i|
    config.vm.define "kafka-#{i}" do |node|
      node.vm.hostname = "kafka-#{i}"
      node.vm.network "private_network", ip: "192.168.56.#{10 + i}"

      # Add 10GB data disk for Kafka storage (Vagrant 2.2.8+)
      node.vm.disk :disk, size: "10GB", name: "data"

      node.vm.provider "virtualbox" do |vb|
        vb.name = "kafka-#{i}"
        vb.memory = 4096
        vb.cpus = 2
      end
    end
  end

  config.vm.define "monitoring-1" do |node|
    node.vm.hostname = "monitoring-1"
    node.vm.network "private_network", ip: "192.168.56.20"

    # Add 10GB data disk for monitoring data
    node.vm.disk :disk, size: "10GB", name: "data"

    node.vm.provider "virtualbox" do |vb|
      vb.name = "monitoring-1"
      vb.memory = 4096
      vb.cpus = 2
    end
  end
end
```

**Step 2: Commit**

```bash
git add tests/vagrant/Vagrantfile
git commit -m "feat(monitoring): update Vagrantfile with monitoring VM and configurable Kafka nodes"
```

---

### Task 12: Update Taskfile

**Files:**
- Modify: `.taskfiles/test.yml`
- Modify: `.taskfiles/ansible.yml`

**Step 1: Update test.yml**

```yaml
version: '3'

vars:
  VAGRANT_DIR: ./tests/vagrant
  INVENTORY: ./inventories/vagrant/hosts.yml
  INVENTORY_CLUSTER: ./inventories/vagrant/hosts-cluster.yml

tasks:
  up:
    desc: "Create test VMs (default: 1 Kafka + monitoring. Use KAFKA_NODES=3 for cluster)"
    dir: "{{.VAGRANT_DIR}}"
    env:
      VAGRANT_EXPERIMENTAL: disks
    cmds:
      - vagrant up

  down:
    desc: Destroy test VMs
    dir: "{{.VAGRANT_DIR}}"
    env:
      VAGRANT_EXPERIMENTAL: disks
    cmds:
      - vagrant destroy -f

  halt:
    desc: Stop test VMs (preserves state)
    dir: "{{.VAGRANT_DIR}}"
    cmds:
      - vagrant halt

  ssh:
    desc: "SSH into a test VM (usage: task test:ssh -- kafka-1)"
    dir: "{{.VAGRANT_DIR}}"
    cmds:
      - vagrant ssh {{.CLI_ARGS | default "kafka-1"}}

  status:
    desc: Show test VM status
    dir: "{{.VAGRANT_DIR}}"
    cmds:
      - vagrant status

  deploy:
    desc: Deploy Kafka to test VMs
    cmds:
      - uv run ansible-playbook -i {{.INVENTORY}} playbooks/kafka.yml

  deploy:monitoring:
    desc: Deploy monitoring stack to test VM
    cmds:
      - uv run ansible-playbook -i {{.INVENTORY}} playbooks/monitoring.yml

  deploy:cluster:
    desc: Deploy 3-node Kafka cluster (requires KAFKA_NODES=3 task test:up)
    cmds:
      - uv run ansible-playbook -i {{.INVENTORY_CLUSTER}} playbooks/kafka.yml

  verify:
    desc: Verify test cluster
    cmds:
      - uv run ansible-playbook -i {{.INVENTORY}} playbooks/verify.yml

  full:
    desc: "Full test cycle (up → deploy Kafka → deploy monitoring → verify)"
    cmds:
      - task: up
      - task: deploy
      - task: deploy:monitoring
      - task: verify
```

**Step 2: Add monitoring tasks to ansible.yml**

Add to `.taskfiles/ansible.yml`:

```yaml
  deploy:monitoring:
    desc: Deploy monitoring stack
    cmds:
      - uv run ansible-playbook -i {{.INVENTORY}} playbooks/monitoring.yml
    preconditions:
      - sh: "test -f {{.INVENTORY}}"
        msg: "Inventory file not found: {{.INVENTORY}}"

  deploy:monitoring:prod:
    desc: Deploy monitoring to production (requires confirmation)
    vars:
      INVENTORY: ./inventories/production/hosts.yml
    cmds:
      - uv run ansible-playbook -i {{.INVENTORY}} playbooks/monitoring.yml
    preconditions:
      - sh: "test -f {{.INVENTORY}}"
        msg: "Production inventory not found: {{.INVENTORY}}"
    prompt: "Deploy monitoring to PRODUCTION? This will modify production servers."
```

**Step 3: Commit**

```bash
git add .taskfiles/test.yml .taskfiles/ansible.yml
git commit -m "feat(monitoring): update Taskfile with monitoring deployment tasks"
```

---

### Task 13: Update production and staging inventories

**Files:**
- Modify: `inventories/production/hosts.yml`
- Modify: `inventories/staging/hosts.yml`
- Create: `inventories/production/group_vars/monitoring.yml`
- Create: `inventories/staging/group_vars/monitoring.yml`

**Step 1: Add monitoring group to production inventory**

Add to the end of `inventories/production/hosts.yml`:

```yaml
    monitoring:
      hosts:
        monitoring-prod:
          ansible_host: <monitoring-vm-private-ip>
      vars:
        ansible_user: ubuntu
        ansible_ssh_private_key_file: ~/.ssh/id_ed25519
```

Add Alloy variables to `inventories/production/group_vars/kafka.yml`:

```yaml
# Alloy remote write endpoints
alloy_victoriametrics_url: "http://<monitoring-vm-private-ip>:8428"
alloy_loki_url: "http://<monitoring-vm-private-ip>:3100"
alloy_environment: "production"
alloy_cluster_name: "kafka-production"
```

**Step 2: Add monitoring group to staging inventory**

Add to the end of `inventories/staging/hosts.yml`:

```yaml
    monitoring:
      hosts:
        monitoring-staging:
          ansible_host: <monitoring-vm-private-ip>
      vars:
        ansible_user: ubuntu
        ansible_ssh_private_key_file: ~/.ssh/id_ed25519
```

Add Alloy variables to `inventories/staging/group_vars/kafka.yml`:

```yaml
# Alloy remote write endpoints
alloy_victoriametrics_url: "http://<monitoring-vm-private-ip>:8428"
alloy_loki_url: "http://<monitoring-vm-private-ip>:3100"
alloy_environment: "staging"
alloy_cluster_name: "kafka-staging"
```

**Note:** Replace `<monitoring-vm-private-ip>` with actual IPs once the monitoring VMs are provisioned.

**Step 3: Commit**

```bash
git add inventories/
git commit -m "feat(monitoring): add monitoring host group to production and staging inventories"
```

---

### Task 14: Local testing with Vagrant

**Step 1: Bring up VMs**

```bash
task test:up
```

Expected: 2 VMs created (kafka-1 + monitoring-1)

**Step 2: Deploy Kafka with Alloy**

```bash
task test:deploy
```

Expected: Kafka + all exporters + Alloy deployed on kafka-1

**Step 3: Deploy monitoring stack**

```bash
task test:deploy:monitoring
```

Expected: Podman containers running on monitoring-1

**Step 4: Verify services**

```bash
# Check Alloy on Kafka node
curl http://192.168.56.11:12345/-/ready

# Check VictoriaMetrics
curl http://192.168.56.20:8428/api/v1/query?query=up

# Check Loki
curl http://192.168.56.20:3100/ready

# Check Grafana
curl http://192.168.56.20:3000/api/health
```

**Step 5: Open Grafana in browser**

Navigate to `http://192.168.56.20:3000` (admin/admin). Verify:
- VictoriaMetrics datasource is connected
- Loki datasource is connected
- Metrics are flowing (check `up` metric in Explore)

---

### Task 15: Create Grafana dashboards

After the stack is running and metrics are flowing, create the dashboard JSON files.

**Files:**
- Create: `monitoring/grafana/provisioning/dashboards/kafka-overview.json`
- Create: `monitoring/grafana/provisioning/dashboards/consumer-lag.json`
- Create: `monitoring/grafana/provisioning/dashboards/jvm-health.json`
- Create: `monitoring/grafana/provisioning/dashboards/node-metrics.json`
- Create: `monitoring/grafana/provisioning/dashboards/monitoring-stack.json`

**Step 1: Build dashboards in Grafana UI**

Use the running Grafana instance to build dashboards interactively. The key panels per dashboard:

**kafka-overview.json:**
- Active controllers (`kafka_controller_active_count`)
- Under-replicated partitions (`kafka_server_replicamanager_underreplicatedpartitions`)
- Messages in per second (`kafka_server_brokertopicmetrics_messagesin_total`)
- Bytes in/out per second

**consumer-lag.json:**
- Consumer group lag (`kafka_consumergroup_lag`)
- Lag trend over time

**jvm-health.json:**
- JVM heap usage (`jvm_memory_bytes_used`)
- GC pause duration (`jvm_gc_collection_seconds_sum`)
- Thread count (`jvm_threads_current`)

**node-metrics.json:**
- Download community dashboard ID 1860 or build custom with `node_*` metrics

**monitoring-stack.json:**
- VictoriaMetrics active time series (`vm_cache_entries`)
- Loki ingestion rate
- Alloy targets up

**Step 2: Export dashboards from Grafana UI as JSON**

Use Grafana's "Share → Export → Save to file" for each dashboard.

**Step 3: Copy exported JSON files to repo**

```bash
cp exported-dashboards/*.json monitoring/grafana/provisioning/dashboards/
git add monitoring/grafana/provisioning/dashboards/*.json
git commit -m "feat(monitoring): add Grafana dashboards for Kafka, JVM, node, and stack monitoring"
```

---

### Task 16: Run ansible-lint

**Step 1: Lint all roles and playbooks**

```bash
uv run ansible-lint roles/alloy/ playbooks/monitoring.yml playbooks/kafka.yml
```

Expected: No errors. Fix any warnings.

**Step 2: Commit any lint fixes**

```bash
git add -A
git commit -m "fix(monitoring): resolve ansible-lint warnings"
```

---

### Task 17: Full end-to-end test

**Step 1: Destroy and recreate from scratch**

```bash
task test:down
task test:full
```

Expected: Clean deployment of Kafka (single node) + monitoring stack, all services healthy.

**Step 2: Verify complete pipeline**

- Metrics visible in VictoriaMetrics (`http://192.168.56.20:8428/vmui/`)
- Logs visible in Grafana Explore via Loki datasource
- Dashboards populated in Grafana

**Step 3: Test with 3-node cluster (optional)**

```bash
task test:down
KAFKA_NODES=3 task test:up
task test:deploy:cluster
task test:deploy:monitoring
```

Verify all 3 Kafka nodes appear in Grafana dashboards.
