# Vagrant Local Testing Design

## Overview

Local testing infrastructure using VirtualBox and Vagrant to replace the previous Lima-based setup. Provides a 3-node Kafka cluster for testing Ansible playbooks locally.

## Decisions

- **VM Management:** Vagrant (declarative, built-in Ansible integration)
- **Base Box:** bento/ubuntu-24.04 (matches production target)
- **Cluster Size:** 3 nodes (tests KRaft quorum and replication)
- **Resources:** 2 vCPU, 4GB RAM per node (6 vCPU, 12GB total)
- **Networking:** Private network with static IPs (192.168.56.11-13)
- **Storage:** 10GB secondary disk per VM for `disk_mount` role testing
- **Inventory:** Static file (IPs are predictable)
- **Workflow:** Taskfile integration (`task test:*` commands)

## Directory Structure

```
kafka-ansible/
├── tests/
│   └── vagrant/
│       ├── Vagrantfile
│       └── .gitignore
├── inventories/
│   └── vagrant/
│       └── hosts.yml
├── .taskfiles/
│   └── test.yml
└── Taskfile.yml
```

## Vagrantfile

```ruby
Vagrant.configure("2") do |config|
  config.vm.box = "bento/ubuntu-24.04"

  (1..3).each do |i|
    config.vm.define "kafka-#{i}" do |node|
      node.vm.hostname = "kafka-#{i}"
      node.vm.network "private_network", ip: "192.168.56.#{10 + i}"

      node.vm.provider "virtualbox" do |vb|
        vb.name = "kafka-#{i}"
        vb.memory = 4096
        vb.cpus = 2

        # Add 10GB data disk for Kafka storage
        data_disk = ".vagrant/kafka-#{i}-data.vdi"
        unless File.exist?(data_disk)
          vb.customize ['createmedium', 'disk', '--filename', data_disk,
                        '--size', 10240, '--format', 'VDI']
        end
        vb.customize ['storageattach', :id, '--storagectl', 'SATA Controller',
                      '--port', 1, '--type', 'hdd', '--medium', data_disk]
      end
    end
  end
end
```

## Static Inventory

```yaml
# inventories/vagrant/hosts.yml
---
all:
  children:
    kafka:
      hosts:
        kafka-1:
          ansible_host: 192.168.56.11
          kafka_node_id: 1
        kafka-2:
          ansible_host: 192.168.56.12
          kafka_node_id: 2
        kafka-3:
          ansible_host: 192.168.56.13
          kafka_node_id: 3
      vars:
        ansible_user: vagrant
        ansible_ssh_private_key_file: "{{ playbook_dir }}/../tests/vagrant/.vagrant/machines/{{ inventory_hostname }}/virtualbox/private_key"
        ansible_ssh_common_args: "-o StrictHostKeyChecking=no"
        kafka_quorum_voters: "1@192.168.56.11:9093,2@192.168.56.12:9093,3@192.168.56.13:9093"
```

## Taskfile

```yaml
# .taskfiles/test.yml
version: '3'

vars:
  VAGRANT_DIR: ./tests/vagrant
  INVENTORY: ./inventories/vagrant/hosts.yml

tasks:
  up:
    desc: Create test VMs
    dir: "{{.VAGRANT_DIR}}"
    cmds:
      - vagrant up

  down:
    desc: Destroy test VMs
    dir: "{{.VAGRANT_DIR}}"
    cmds:
      - vagrant destroy -f

  halt:
    desc: Stop test VMs (preserves state)
    dir: "{{.VAGRANT_DIR}}"
    cmds:
      - vagrant halt

  ssh:
    desc: "SSH into a test VM (usage: task test:ssh -- 1)"
    dir: "{{.VAGRANT_DIR}}"
    cmds:
      - vagrant ssh kafka-{{.CLI_ARGS | default "1"}}

  status:
    desc: Show test VM status
    dir: "{{.VAGRANT_DIR}}"
    cmds:
      - vagrant status

  deploy:
    desc: Deploy Kafka to test VMs
    cmds:
      - uv run ansible-playbook -i {{.INVENTORY}} playbooks/kafka.yml

  verify:
    desc: Verify test cluster
    cmds:
      - uv run ansible-playbook -i {{.INVENTORY}} playbooks/verify.yml

  full:
    desc: Full test cycle (up → deploy → verify)
    cmds:
      - task: up
      - task: deploy
      - task: verify
```

## Commands

| Command | Description |
|---------|-------------|
| `task test:up` | Create 3 VMs |
| `task test:down` | Destroy VMs |
| `task test:halt` | Stop VMs (keep state) |
| `task test:status` | Show VM status |
| `task test:ssh -- 1` | SSH into kafka-1 |
| `task test:deploy` | Run Kafka playbook |
| `task test:verify` | Verify cluster |
| `task test:full` | Full cycle (up → deploy → verify) |

## Requirements

- VirtualBox installed
- Vagrant installed
- ~12GB RAM available on host
