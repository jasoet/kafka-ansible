# Grafana Monitoring Stack Design

**Date**: 2026-02-09
**Status**: Draft

## Overview

Deploy a self-hosted monitoring stack on a dedicated EC2 instance in the same VPC as the Kafka cluster (ap-southeast-1). All monitoring services run as Podman containers managed via Quadlet (systemd-native). Grafana Alloy is installed on each Kafka node as a systemd service for local metric scraping and log shipping.

## Components

| Component | Role | Deployment |
|---|---|---|
| **Grafana** | Dashboards, visualization, alerting | Podman container (monitoring VM) |
| **VictoriaMetrics** | Metrics storage (Prometheus-compatible) | Podman container (monitoring VM) |
| **Grafana Loki** | Log aggregation | Podman container (monitoring VM) |
| **Grafana Alloy** | Telemetry collector (monitoring VM self-monitoring) | Podman container (monitoring VM) |
| **Grafana Alloy** | Metric scraping + log shipping | Systemd service (each Kafka node) |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│            Monitoring VM (EC2, same VPC)             │
│                                                     │
│  ┌──────────┐ ┌──────────────┐ ┌──────────┐        │
│  │ Grafana  │ │VictoriaMetrics│ │   Loki   │        │
│  │  :3000   │ │    :8428     │ │  :3100   │        │
│  └──────────┘ └──────────────┘ └──────────┘        │
│  ┌──────────────────────────────────────┐           │
│  │  Alloy (self-monitoring + host)      │           │
│  │  scrape: VM, Loki, Grafana metrics   │           │
│  │  collect: container logs             │           │
│  │  built-in: node_exporter integration │           │
│  └──────────────────────────────────────┘           │
│  Podman Quadlet + systemd                           │
└────────────────────────▲────────────────────────────┘
                         │ remote-write (metrics + logs)
          ┌──────────────┼──────────────┐
     ┌────┴─────┐   ┌───┴──────┐  ┌────┴─────┐
     │ Kafka-1  │   │ Kafka-2  │  │ Kafka-3  │
     │ Alloy    │   │ Alloy    │  │ Alloy    │
     │ ├ scrape │   │ ├ scrape │  │ ├ scrape │
     │ │ :9100  │   │ │ :9100  │  │ │ :9100  │
     │ │ :7071  │   │ │ :7071  │  │ │ :7071  │
     │ │ :9308  │   │ │ :9308  │  │ │ :9308  │
     │ └ logs   │   │ └ logs   │  │ └ logs   │
     │  kafka/  │   │  kafka/  │  │  kafka/  │
     └──────────┘   └──────────┘  └──────────┘
```

## Data Flow

1. **Alloy on each Kafka node** scrapes localhost exporters (Node Exporter :9100, JMX Exporter :7071, Kafka Exporter :9308) every 15s
2. **Alloy on each Kafka node** tails Kafka logs from `/opt/kafka/logs/*.log`
3. Metrics are remote-written to **VictoriaMetrics** on the monitoring VM (:8428)
4. Logs are pushed to **Loki** on the monitoring VM (:3100)
5. **Alloy on monitoring VM** scrapes VictoriaMetrics, Loki, and Grafana `/metrics` endpoints, collects container logs, and uses built-in node_exporter integration for host metrics
6. **Grafana** queries VictoriaMetrics (as Prometheus datasource) and Loki for dashboards and alerting

## Labels

All metrics include these labels (sourced from Ansible inventory variables):
- `cluster` - cluster name
- `node` - node hostname
- `environment` - staging or production

## Container Configuration

### compose.yaml (source of truth)

| Container | Image | Port | Volume |
|---|---|---|---|
| VictoriaMetrics | `victoriametrics/victoria-metrics` | `:8428` | `/data/monitoring/victoriametrics` |
| Loki | `grafana/loki` | `:3100` | `/data/monitoring/loki` |
| Grafana | `grafana/grafana` | `:3000` | `/data/monitoring/grafana` + provisioning |
| Alloy | `grafana/alloy` | `:12345` (UI) | `/proc`, `/sys` (read-only for host metrics) |

### Container Management

- **Source of truth**: `monitoring/compose.yaml` in the repo
- **Conversion**: `podlets compose compose.yaml` generates Quadlet unit files (run locally, committed to repo)
- **Runtime**: Quadlet `.container` files deployed to `/etc/containers/systemd/` on the monitoring VM
- **Lifecycle**: systemd manages all containers natively

### Network

Single shared Podman network. Containers communicate by service name.

### Retention

| Component | Retention | Configurable via |
|---|---|---|
| VictoriaMetrics | 30 days (production), 7 days (staging) | `-retentionPeriod` flag |
| Loki | 30 days (production), 7 days (staging) | `limits_config.retention_period` |

### Data Persistence

All data stored under `/data/monitoring/` (dedicated disk mount, consistent with Kafka's `/data/kafka` pattern):
- `/data/monitoring/victoriametrics/`
- `/data/monitoring/loki/`
- `/data/monitoring/grafana/`

## Alloy Configuration

### On Kafka Nodes (systemd service)

- Scrapes localhost:9100 (Node Exporter), :7071 (JMX Exporter), :9308 (Kafka Exporter)
- Tails `/opt/kafka/logs/*.log`
- Remote-writes metrics to `<monitoring-vm-private-ip>:8428`
- Pushes logs to `<monitoring-vm-private-ip>:3100`
- Scrape interval: 15s

### On Monitoring VM (Podman container)

- Built-in node_exporter integration for host metrics (CPU, memory, disk, network)
- Scrapes `victoriametrics:8428/metrics`, `loki:3100/metrics`, `grafana:3000/metrics`
- Collects container logs via Podman journal
- Writes metrics to `victoriametrics:8428`
- Pushes logs to `loki:3100`

## Grafana Provisioning

Dashboards and datasources are auto-provisioned (no manual setup).

### Datasources

- **VictoriaMetrics**: Prometheus type, URL `http://victoriametrics:8428`
- **Loki**: Loki type, URL `http://loki:3100`

### Pre-provisioned Dashboards

| Dashboard | Source | Key Panels |
|---|---|---|
| Kafka Overview | Custom | Broker status, messages in/out rate, active controllers, under-replicated partitions |
| Consumer Lag | Custom | Per-group lag, lag trend over time |
| JVM Health | Custom | Heap usage, GC pauses, thread count per broker |
| Node Metrics | Community (ID: 1860) | CPU, memory, disk I/O, network per host |
| Monitoring Stack | Custom | VictoriaMetrics ingestion rate, Loki storage, Alloy pipeline health |

### Alerting

Grafana built-in alerting configured with alert rules only (no external notification channels initially). Notification destinations to be added later (Slack, email, PagerDuty, etc.).

## Monitoring VM Sizing

| | Staging | Production |
|---|---|---|
| vCPU | 2 | 4 |
| RAM | 4 GB | 8 GB |
| Data disk | 50 GB | 200 GB |
| Instance type | `t4g.medium` | `t4g.xlarge` |
| Retention | 7 days | 30 days |

ARM64 (t4g) for consistency with Kafka nodes and cost efficiency.

## Ansible Structure

### New Role: `alloy`

Deploys Grafana Alloy as a systemd service on Kafka nodes:
- Downloads Alloy binary
- Templates config with local scrape targets and remote-write endpoints
- Manages systemd service

### New Playbook: `playbooks/monitoring.yml`

Deploys the monitoring stack to the monitoring VM:
1. Install Podman
2. Mount data disk to `/data/monitoring/`
3. Deploy Quadlet unit files to `/etc/containers/systemd/`
4. Deploy Alloy, Loki, and Grafana configs
5. Start services via systemd
6. Post-task: display Grafana URL and endpoints

### New Inventory Group

```ini
[monitoring]
monitoring-vm ansible_host=<private-ip>

[kafka]
kafka-1 ...
kafka-2 ...
kafka-3 ...
```

### Repository Structure (new additions)

```
roles/alloy/                          # Alloy agent on Kafka nodes
  ├── defaults/main.yml
  ├── tasks/main.yml
  ├── templates/config.alloy.j2
  └── handlers/main.yml

playbooks/monitoring.yml              # Monitoring stack deployment

monitoring/                           # Monitoring stack configs
  ├── compose.yaml                    # Source of truth
  ├── quadlet/                        # Generated by podlets (committed)
  │   ├── grafana.container
  │   ├── victoriametrics.container
  │   ├── loki.container
  │   ├── alloy.container
  │   └── monitoring.network
  ├── alloy/config.alloy              # Alloy config for monitoring VM
  ├── grafana/
  │   └── provisioning/
  │       ├── datasources/default.yaml
  │       └── dashboards/
  │           ├── dashboard.yaml
  │           ├── kafka-overview.json
  │           ├── consumer-lag.json
  │           ├── jvm-health.json
  │           └── monitoring-stack.json
  ├── loki/config.yaml
  └── victoriametrics/                # (minimal, mostly CLI flags)
```

## Local Testing (Vagrant)

### Default Topology (2 VMs)

The default test setup uses **1 Kafka node + 1 monitoring VM** for fast, resource-friendly full-pipeline testing:

| VM | Hostname | IP | vCPU | RAM | Disk | Purpose |
|---|---|---|---|---|---|---|
| kafka-1 | kafka-1 | 192.168.56.11 | 2 | 4 GB | 10 GB | Kafka broker (single-node KRaft) + Alloy |
| monitoring-1 | monitoring-1 | 192.168.56.20 | 2 | 4 GB | 10 GB | Grafana + VictoriaMetrics + Loki + Alloy |

### Full Cluster Topology (4 VMs)

For multi-node cluster testing, additional Kafka nodes can be brought up:

| VM | Hostname | IP | vCPU | RAM | Disk | Purpose |
|---|---|---|---|---|---|---|
| kafka-1 | kafka-1 | 192.168.56.11 | 2 | 4 GB | 10 GB | Kafka broker + Alloy |
| kafka-2 | kafka-2 | 192.168.56.12 | 2 | 4 GB | 10 GB | Kafka broker + Alloy |
| kafka-3 | kafka-3 | 192.168.56.13 | 2 | 4 GB | 10 GB | Kafka broker + Alloy |
| monitoring-1 | monitoring-1 | 192.168.56.20 | 2 | 4 GB | 10 GB | Grafana + VictoriaMetrics + Loki + Alloy |

### Vagrantfile Changes

Add `monitoring-1` at `192.168.56.20`. Kafka nodes use a configurable count (default: 1, max: 3) via `KAFKA_NODES` environment variable:

```bash
task test:up                     # default: kafka-1 + monitoring-1
KAFKA_NODES=3 task test:up       # full: kafka-1,2,3 + monitoring-1
```

### Vagrant Inventory

Single-node Kafka inventory for default testing (single-node KRaft mode):

```yaml
all:
  children:
    kafka:
      hosts:
        kafka-1:
          ansible_host: 192.168.56.11
          kafka_node_id: 1
          kafka_internal_ip: 192.168.56.11
      vars:
        kafka_quorum_voters: "1@192.168.56.11:9093"
    monitoring:
      hosts:
        monitoring-1:
          ansible_host: 192.168.56.20
```

A separate `hosts-cluster.yml` inventory is available for 3-node testing.

### Taskfile Tasks

| Task | Description |
|---|---|
| `test:up` | Create VMs (default: 1 Kafka + 1 monitoring) |
| `test:deploy` | Deploy Kafka (single node) + Alloy to Vagrant |
| `test:deploy:monitoring` | Deploy monitoring stack to Vagrant monitoring VM |
| `test:full` | Full cycle: up → deploy Kafka → deploy monitoring → verify |
| `test:deploy:cluster` | Deploy 3-node Kafka cluster (requires `KAFKA_NODES=3 task test:up`) |

### Default Full Test Flow

```bash
task test:full
# Equivalent to:
#   1. task test:up              (kafka-1 + monitoring-1)
#   2. task test:deploy          (Kafka single-node + Alloy)
#   3. task test:deploy:monitoring (monitoring stack)
#   4. task test:verify          (verify everything)
```

This tests the complete pipeline (Kafka → Alloy → VictoriaMetrics/Loki → Grafana) with only 2 VMs (~8 GB RAM total).

## Implementation Order

1. Set up `monitoring/compose.yaml` and container configs
2. Generate Quadlet files with `podlets`
3. Create `playbooks/monitoring.yml` (Podman + Quadlet deployment)
4. Create `roles/alloy` (Kafka node agent)
5. Add `alloy` role to `playbooks/kafka.yml`
6. Add Grafana provisioning (datasources + dashboards)
7. Update inventories with monitoring host group (production, staging, vagrant)
8. Update Vagrantfile with monitoring VM
9. Update Taskfile with monitoring tasks
10. Test locally with Vagrant (full stack or single-node + monitoring)
11. Test on staging (single Kafka node + monitoring VM)
