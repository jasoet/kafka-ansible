# Analytics Platform Architecture Overview

## Purpose

This document is the single source of truth for the analytics data pipeline infrastructure. It covers the full system architecture — EKS services, Kafka cluster, networking, and data flow — to provide operational reference for the engineering team.

---

## System Overview

The analytics platform collects user behavior data from hundreds of websites and mobile applications, processes it through a high-throughput pipeline, and stores it as Parquet files in S3 for analysis.

```
Analytics Traffic
       │
       ▼
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐     ┌─────┐
│   Backend    │────▶│   Apache Kafka   │────▶│   Packager   │────▶│  S3 │
│  (EKS Pod)   │     │  (EC2 Cluster)   │     │  (EKS Pod)   │     │     │
│  Producer    │     │  3-node KRaft    │     │  Consumer    │     │     │
└──────────────┘     └──────────────────┘     └──────────────┘     └─────┘
      EKS                   EC2                    EKS
  Private Subnet        Public Subnet          Private Subnet
```

**Traffic profile:** ~10,000 events/sec at ~2KB per message, with spiky bursts during campaigns and peak hours.

**Pipeline stages:**

1. **Backend** (EKS) — Receives analytics events from web/mobile, produces messages to Kafka
2. **Kafka** (EC2) — Durable message buffer, 3-node cluster with replication factor 3
3. **Packager** (EKS) — Consumes messages, enriches data, batches into Parquet files, uploads to S3

---

## VPC & Networking

All infrastructure runs in a single VPC in **ap-southeast-1 (Singapore)**.

### Network Layout

```
VPC: 10.100.0.0/16
│
├── Public Subnet 1: 10.100.1.0/24  (AZ-a)
│   ├── NAT Gateway 1
│   └── Kafka staging node (10.100.1.42)
│
├── Public Subnet 2: 10.100.2.0/24  (AZ-b)
│   ├── NAT Gateway 2
│   └── Kafka production nodes (10.100.2.86, 10.100.2.118, 10.100.2.117)
│
├── Private Subnet 1: 10.100.4.0/24  (AZ-a)
│   └── EKS worker nodes
│
└── Private Subnet 2: 10.100.5.0/24  (AZ-b)
    └── EKS worker nodes
```

### Routing

| Subnet Type | Internet Access | Route |
|---|---|---|
| Public | Direct via Internet Gateway | 0.0.0.0/0 → IGW |
| Private 1 | Outbound only via NAT Gateway 1 | 0.0.0.0/0 → NAT-GW-1 |
| Private 2 | Outbound only via NAT Gateway 2 | 0.0.0.0/0 → NAT-GW-2 |

### Cross-Component Communication

EKS pods (private subnets) communicate with Kafka brokers (public subnets) directly over **private IPs** within the VPC. No traffic leaves the VPC for this communication.

```
EKS Pod (10.100.4.x) ──── VPC internal ────▶ Kafka Broker (10.100.2.86:9092)
```

### SSH Access for Ansible

Kafka EC2 instances are in the public subnet to allow SSH access during Ansible provisioning. Access is temporarily whitelisted by the engineer's public IP, then removed after setup. Day-to-day inter-broker and client communication uses private IPs.

---

## EKS Cluster

Managed by **CloudFormation** (`cloudformation-eks-cluster.yaml`). The EKS cluster hosts the Backend and Packager services.

### Cluster Configuration

| Property | Value |
|---|---|
| Kubernetes Version | 1.35 |
| Region | ap-southeast-1 |
| Cluster Security Group | Allows all traffic within the group |
| Subnets | All 4 (public + private) |
| IAM Role | AmazonEKSClusterPolicy, AmazonEKSVPCResourceController |

### Node Groups

| Node Group | Purpose | Instance Type | Architecture | Scaling | Subnets |
|---|---|---|---|---|---|
| **p-analytics-tracker-ng** | Production workloads | c7g.2xlarge (8 vCPU, 16GB) | ARM64 | 1-2 nodes | Private 1 & 2 |
| **s-analytics-tracker-ng** | Staging workloads | t4g.medium (2 vCPU, 4GB) | ARM64 | 1-2 nodes | Private 1 & 2 |

Both node groups use:
- **AMI:** AL2023_ARM_64_STANDARD
- **Disk:** 80GB gp3 (3000 IOPS, 125 MB/s throughput)
- **Metadata:** IMDSv1/v2 (HttpTokens optional, hop limit 2)

### Node IAM Permissions

EKS worker nodes have the following managed policies:
- AmazonEC2ContainerRegistryReadOnly
- AmazonEKSWorkerNodePolicy
- AmazonEKS_CNI_Policy
- AmazonSSMManagedInstanceCore

### EFS (Optional)

Controlled by the `EfsEnable` parameter (default: `true`).

| Property | Value |
|---|---|
| Encryption | Enabled |
| Performance Mode | generalPurpose |
| Throughput Mode | bursting |
| Mount Targets | Private Subnet 1 & 2 |
| Access | NFS (port 2049) from EKS cluster security group |

---

## Kafka Cluster (EC2)

Managed by **Ansible** (this repository). EC2 instances are provisioned manually, then configured via Ansible playbooks.

### Production Cluster (3-node)

| Node | Public DNS | Private IP | Node ID |
|---|---|---|---|
| Broker 1 | ec2-54-179-198-162.ap-southeast-1.compute.amazonaws.com | 10.100.2.86 | 1 |
| Broker 2 | ec2-54-179-72-89.ap-southeast-1.compute.amazonaws.com | 10.100.2.118 | 2 |
| Broker 3 | ec2-54-179-151-161.ap-southeast-1.compute.amazonaws.com | 10.100.2.117 | 3 |

**Quorum voters:** `1@10.100.2.86:9093,2@10.100.2.118:9093,3@10.100.2.117:9093`

### Staging Cluster (single-node)

| Node | Public DNS | Private IP | Node ID |
|---|---|---|---|
| Broker 1 | ec2-3-0-99-176.ap-southeast-1.compute.amazonaws.com | 10.100.1.42 | 1 |

### Kafka Configuration

| Property | Production | Staging |
|---|---|---|
| Kafka Version | 4.1.1 (Scala 2.13) | 4.1.1 (Scala 2.13) |
| Mode | KRaft (combined broker + controller) | KRaft (combined) |
| Replication Factor | 3 | 1 |
| Min In-Sync Replicas | 2 | 1 |
| Retention | 72 hours, 50GB/partition | 24 hours, 10GB/partition |
| Data Directory | /data/kafka (dedicated disk) | /data/kafka |
| Client Port | 9092 | 9092 |
| Controller Port | 9093 | 9093 |
| Max Message Size | 1MB | 1MB |
| Segment Size | 512MB | 512MB |

### Resource Tuning (Auto-scaled to VM)

| Parameter | Formula | Example (16 vCPU, 64GB) |
|---|---|---|
| Heap Size | 25% RAM (min 1GB, max 8GB) | 8GB |
| Network Threads | vCPU / 2 (min 1, max 3) | 3 |
| IO Threads | vCPU x 2 (min 4, max 8) | 8 |

### VM Requirements

| Property | Production | Staging |
|---|---|---|
| OS | Ubuntu 24.04 LTS (aarch64) | Ubuntu 24.04 LTS (aarch64) |
| vCPU | 8 min, 16 recommended | 2 min |
| RAM | 16GB min, 32GB recommended | 4GB min |
| Disk | 2TB dedicated | 50GB min |
| Disk Filesystem | XFS (noatime, nodiratime) | XFS |

### Monitoring Agents on Each Broker

| Agent | Port | Purpose |
|---|---|---|
| JMX Exporter | 7071 | Kafka/JVM internal metrics |
| Kafka Exporter | 9308 | Consumer lag, broker-level metrics |
| Node Exporter | 9100 | Server hardware metrics (CPU, memory, disk) |
| Alloy | 12345 | Metrics & logs collection agent |

---

## Component Inventory

| Component | Managed By | Infra Type | Instance/Resource | Environment |
|---|---|---|---|---|
| VPC, Subnets, IGW, NAT | CloudFormation (cloudformation-eks-cluster.yaml) | Networking | — | Shared |
| EKS Control Plane | CloudFormation (cloudformation-eks-cluster.yaml) | Managed K8s | — | Shared |
| EKS Prod Node Group | CloudFormation (cloudformation-eks-cluster.yaml) | EC2 (via ASG) | c7g.2xlarge | Production |
| EKS Staging Node Group | CloudFormation (cloudformation-eks-cluster.yaml) | EC2 (via ASG) | t4g.medium | Staging |
| EFS File System | CloudFormation (cloudformation-eks-cluster.yaml) | Managed Storage | — | Shared |
| Kafka Prod Brokers (x3) | Ansible (kafka-ansible) | EC2 (manual) | Varies | Production |
| Kafka Staging Broker (x1) | Ansible (kafka-ansible) | EC2 (manual) | Varies | Staging |
| Monitoring VM | Manual (pending decision) | EC2 (manual) | Varies | Shared |
| Backend Service | kubectl / CI/CD | EKS Deployment | — | Prod & Staging |
| Packager Service | kubectl / CI/CD | EKS Deployment | — | Prod & Staging |

---

## Monitoring

Monitoring architecture decision is pending. See [Kafka Infrastructure Monitoring Specification](2026-02-09-kafka-infrastructure-monitoring-spec.md) for the four evaluated options.

**Current state:** Monitoring agents (JMX Exporter, Kafka Exporter, Node Exporter, Alloy) are installed and running on all Kafka brokers. The visualization and alerting layer is not yet configured.

---

## Infrastructure Management Summary

| Layer | Tool | Source of Truth |
|---|---|---|
| VPC, EKS, Networking | AWS CloudFormation | `cloudformation-eks-cluster.yaml` |
| Kafka Configuration | Ansible | `kafka-ansible` repository |
| Kafka EC2 Provisioning | Manual | — |
| EKS Workloads | kubectl / CI/CD | Application repositories |
| Monitoring | Pending | — |
