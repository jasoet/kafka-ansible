# Node Exporter Role Design

## Overview

Add Node Exporter to Kafka cluster nodes for host-level metrics (CPU, memory, disk, network).

## Decisions

- **Installation method**: Download binary from GitHub (consistent with kafka_exporter)
- **Port**: 9100 (default)
- **Collectors**: Default collectors (full metrics)
- **User**: Dedicated `node_exporter` system user

## Structure

```
roles/node_exporter/
├── defaults/main.yml
├── tasks/main.yml
├── templates/node-exporter.service.j2
└── handlers/main.yml
```

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `node_exporter_version` | `1.9.0` | Version to install |
| `node_exporter_port` | `9100` | Listen port |
| `node_exporter_user` | `node_exporter` | System user |
| `node_exporter_group` | `node_exporter` | System group |
| `node_exporter_install_dir` | `/opt/node_exporter` | Install location |

## Implementation

### tasks/main.yml

1. Create system group and user (no login shell)
2. Create install directory
3. Download binary from GitHub releases (with retries)
4. Extract tarball
5. Deploy systemd service
6. Enable and start service

### Systemd Service

- Run as `node_exporter` user
- Restart on failure
- Listen on `0.0.0.0:9100`
- Log to journald

## Files to Modify

- `playbooks/kafka.yml` - Add `node_exporter` role after `kafka_exporter`
- `playbooks/verify.yml` - Add port 9100 check and metrics verification
- `playbooks/precheck.yml` - Add download URL reachability check

## Metrics Endpoint

Each node exposes: `http://<node-ip>:9100/metrics`
