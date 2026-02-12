# Analytics Platform Scaling Playbook

## Purpose

This document is the engineer's handbook for manually scaling the analytics pipeline. All scaling decisions are made by engineers based on monitoring data — no auto-scaling is currently configured.

---

## Scaling Philosophy

| Component | Strategy | Rationale |
|---|---|---|
| **Kafka** | Over-provision for peak, scale vertically when outgrown | Adding/removing brokers requires partition rebalancing — a heavy operation. Simpler to size for peak and accept off-peak over-provisioning. |
| **Backend (producer)** | Scale horizontally via pod replicas, then nodes | Spiky traffic hits the producer first. Pod scaling is fast (~seconds). Node scaling is slower (~minutes) but needed when pods can't schedule. |
| **Packager (consumer)** | Scale horizontally via pod replicas + partitions | Consumer parallelism is bounded by partition count. Scaling replicas beyond partition count has no effect. |

### Decision Flow

```
Monitoring signal detected
       │
       ▼
Is it a Kafka issue?
  ├── Yes → Section: Kafka Scaling Procedures
  └── No
       │
       ▼
Is it a pod resource issue?
  ├── Yes → Section: EKS Pod Scaling
  └── No
       │
       ▼
Are pods pending/unschedulable?
  ├── Yes → Section: EKS Node Scaling
  └── No → Investigate application-level issue
```

---

## Monitoring Signals

Before scaling, verify which component is the bottleneck. These are the key metrics to watch for each component.

### Backend (Producer)

| Metric | Normal | Warning | Action |
|---|---|---|---|
| Request latency (p99) | < 100ms | > 500ms | Scale Backend pods |
| Pod CPU utilization | < 60% | > 80% sustained | Scale Backend pods |
| Pod memory utilization | < 70% | > 85% sustained | Scale Backend pods or increase limits |
| Kafka produce errors | 0 | Any errors | Check Kafka health first, then scale if Kafka is healthy |
| Produce latency to Kafka | < 50ms | > 200ms | Check Kafka disk/network, may need Kafka vertical scale |

### Packager (Consumer)

| Metric | Normal | Warning | Action |
|---|---|---|---|
| Consumer lag (messages) | < 100,000 | > 500,000 and growing | Scale Packager pods (up to partition count) |
| Batch processing time | Stable | Increasing trend | Scale Packager pods or investigate enrichment logic |
| S3 upload duration | < 5s | > 15s | Check S3 throttling, not a scaling issue |
| Pod CPU utilization | < 60% | > 80% sustained | Scale Packager pods |

### Kafka Brokers

| Metric | Normal | Warning | Action |
|---|---|---|---|
| Broker disk usage | < 60% | > 75% | Expand EBS volume or reduce retention |
| Network throughput | < 60% capacity | > 80% capacity | Vertical scale (larger instance) |
| Under-replicated partitions | 0 | > 0 | Investigate broker health, not a scaling issue |
| JVM heap usage | < 70% | > 80% sustained | Increase heap or vertical scale |
| GC pause time | < 100ms | > 500ms | Increase heap or vertical scale |
| Request queue size | < 10 | > 50 sustained | Vertical scale (more CPU/network) |

### EKS Nodes

| Metric | Normal | Warning | Action |
|---|---|---|---|
| Node CPU utilization | < 70% | > 85% sustained | Scale node group |
| Node memory utilization | < 75% | > 85% sustained | Scale node group |
| Pods in Pending state | 0 | Any pods pending | Scale node group |
| Pod scheduling failures | 0 | Any failures | Scale node group or check resource requests |

---

## EKS Scaling Procedures

### Pod Scaling (Backend)

**When:** Backend request latency or CPU exceeds warning thresholds.

**Step 1:** Check current state
```bash
kubectl get deployment backend -n <namespace> -o wide
kubectl top pods -n <namespace> -l app=backend
```

**Step 2:** Scale replicas
```bash
kubectl scale deployment backend -n <namespace> --replicas=<N>
```

**Step 3:** Verify pods are running
```bash
kubectl get pods -n <namespace> -l app=backend -w
```

**Step 4:** Verify metrics improve — check request latency and CPU utilization return to normal range.

**Recommended replica counts:**

| Traffic Level | Approximate Events/sec | Suggested Replicas |
|---|---|---|
| Low (off-peak) | < 5,000 | 2 |
| Normal | ~10,000 | 3-4 |
| High (campaign/peak) | 20,000-30,000 | 6-8 |
| Spike | > 30,000 | 10+ (ensure node capacity) |

> Adjust these based on observed pod resource consumption. These are starting points.

### Pod Scaling (Packager)

**When:** Consumer lag is growing and Packager CPU is saturated.

**Important:** Packager parallelism is bounded by the number of Kafka topic partitions. If you have 10 partitions, running more than 10 Packager replicas provides no benefit — extra replicas will sit idle.

**Step 1:** Check current lag and partition count
```bash
# Check consumer lag
kubectl exec -it <kafka-pod-or-use-ssh> -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server <broker>:9092 \
  --group <packager-consumer-group> \
  --describe

# Check partition count for the topic
kubectl exec -it <kafka-pod-or-use-ssh> -- \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --topic <topic-name> \
  --describe
```

**Step 2:** Scale replicas (do not exceed partition count)
```bash
kubectl scale deployment packager -n <namespace> --replicas=<N>
```

**Step 3:** Monitor consumer lag decreasing
```bash
# Watch lag over time — it should decrease
watch -n 10 'kubectl exec -it <kafka-pod-or-use-ssh> -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server <broker>:9092 \
  --group <packager-consumer-group> \
  --describe'
```

**Step 4:** If lag is not decreasing despite max replicas, increase partition count (see Kafka section).

### Node Scaling (CloudFormation)

**When:** Pods are in Pending state due to insufficient node resources, or node CPU/memory consistently exceeds 85%.

**Step 1:** Confirm pods are unschedulable
```bash
kubectl get pods -A --field-selector=status.phase=Pending
kubectl describe pod <pending-pod> -n <namespace>
# Look for: "Insufficient cpu" or "Insufficient memory" in Events
```

**Step 2:** Update CloudFormation stack

For production node group (`p-analytics-tracker-ng`):
```bash
aws cloudformation update-stack \
  --stack-name <stack-name> \
  --use-previous-template \
  --parameters \
    ParameterKey=NodeGroupInstanceTypes,ParameterValue=c7g.2xlarge \
    ParameterKey=VPCCidrBlock,UsePreviousValue=true \
    ParameterKey=PublicCidrBlock1,UsePreviousValue=true \
    ParameterKey=PublicCidrBlock2,UsePreviousValue=true \
    ParameterKey=PrivateCidrBlock1,UsePreviousValue=true \
    ParameterKey=PrivateCidrBlock2,UsePreviousValue=true \
    ParameterKey=EKSClusterVersion,UsePreviousValue=true \
    ParameterKey=EfsEnable,UsePreviousValue=true \
  --capabilities CAPABILITY_NAMED_IAM
```

> **Note:** The current CloudFormation template has `DesiredSize`, `MinSize`, and `MaxSize` hardcoded in the template (not parameterized). To change node counts, update the template directly and run a stack update. Consider parameterizing these values for easier scaling.

**Step 3:** Wait for new nodes to join
```bash
kubectl get nodes -w
# Wait for new node to show Ready status
```

**Step 4:** Verify pending pods are now scheduled
```bash
kubectl get pods -A --field-selector=status.phase=Pending
# Should return no results
```

---

## Kafka Scaling Procedures

### Vertical Scaling (Instance Type Upgrade)

**When:** Broker disk I/O, network throughput, or CPU consistently exceeds capacity. This is a planned maintenance operation.

**Pre-requisites:**
- Kafka cluster has replication factor ≥ 2 (production: 3)
- Min in-sync replicas allows one broker to be offline (production: 2 of 3)

**Procedure (one broker at a time — rolling upgrade):**

**Step 1:** Pick the broker to upgrade (start with any non-controller-leader)

**Step 2:** Gracefully stop Kafka on the target broker
```bash
# SSH to the broker
sudo systemctl stop kafka
```

**Step 3:** Verify cluster health (remaining brokers)
```bash
# From another broker
/opt/kafka/bin/kafka-metadata.sh --snapshot /data/kafka/__cluster_metadata-0/00000000000000000000.log --cluster-id <cluster-id>
```

**Step 4:** Stop the EC2 instance
```bash
aws ec2 stop-instances --instance-ids <instance-id>
aws ec2 wait instance-stopped --instance-ids <instance-id>
```

**Step 5:** Change instance type
```bash
aws ec2 modify-instance-attribute \
  --instance-id <instance-id> \
  --instance-type <new-type>
```

**Step 6:** Start instance and Kafka
```bash
aws ec2 start-instances --instance-ids <instance-id>
aws ec2 wait instance-running --instance-ids <instance-id>

# SSH to broker
sudo systemctl start kafka
```

**Step 7:** Verify broker rejoins cluster and partitions are in-sync
```bash
/opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --describe \
  --under-replicated-partitions
# Should return no results once fully caught up
```

**Step 8:** Repeat for remaining brokers (one at a time, wait for full sync between each)

### Adding Partitions

**When:** Consumer lag is growing and Packager replicas are already at the partition count limit.

**Important:** Partitions can be increased but **never decreased**. Plan partition counts carefully.

**Step 1:** Check current partition count
```bash
/opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --topic <topic-name> \
  --describe
```

**Step 2:** Increase partition count
```bash
/opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --topic <topic-name> \
  --alter \
  --partitions <new-count>
```

**Step 3:** Scale Packager replicas to match new partition count (see EKS Pod Scaling section)

**Step 4:** Verify even distribution across brokers
```bash
/opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --topic <topic-name> \
  --describe
# Check partition leaders are distributed across all brokers
```

**Guidelines for partition count:**

| Events/sec | Suggested Partitions | Max Packager Replicas |
|---|---|---|
| < 10,000 | 10 | 10 |
| 10,000-30,000 | 20-30 | 20-30 |
| 30,000-100,000 | 50 | 50 |
| > 100,000 | 100+ (test first) | 100+ |

> **Warning:** Adding partitions to a topic with key-based partitioning will change the partition assignment for keys. If the Packager relies on key ordering, coordinate this change carefully.

### Disk Expansion (EBS Volume Resize)

**When:** Broker disk usage exceeds 75%. This is a non-disruptive, online operation.

**Step 1:** Identify the EBS volume attached to the broker
```bash
aws ec2 describe-instances \
  --instance-ids <instance-id> \
  --query 'Reservations[].Instances[].BlockDeviceMappings[]'
```

**Step 2:** Resize the volume (online, no downtime)
```bash
aws ec2 modify-volume \
  --volume-id <volume-id> \
  --size <new-size-gb>

# Wait for modification to complete
aws ec2 describe-volumes-modifications \
  --volume-ids <volume-id>
```

**Step 3:** Extend the filesystem on the broker
```bash
# SSH to the broker
sudo xfs_growfs /data/kafka
```

**Step 4:** Verify new size
```bash
df -h /data/kafka
```

### Alternative: Reduce Retention

If disk pressure is temporary and data retention can be shortened:

```bash
# Reduce retention to 48 hours (from 72)
/opt/kafka/bin/kafka-configs.sh \
  --bootstrap-server <broker>:9092 \
  --alter \
  --entity-type topics \
  --entity-name <topic-name> \
  --add-config retention.ms=172800000
```

---

## Scaling Decision Matrix

Quick reference for common scenarios:

| Symptom | First Action | If Insufficient |
|---|---|---|
| High Backend latency | Scale Backend pods | Scale EKS nodes |
| Growing consumer lag | Scale Packager pods (up to partition count) | Add partitions, then more pods |
| Kafka disk > 75% | Expand EBS volume or reduce retention | Vertical scale to larger instance |
| Kafka network saturated | Vertical scale (larger instance) | Consider adding brokers (major operation) |
| Kafka high GC pauses | Increase heap size via Ansible | Vertical scale |
| Pods stuck Pending | Scale EKS node group via CloudFormation | Upgrade to larger instance type |
| All pods healthy but slow | Check application metrics, not infra | Profile application code |

---

## Pending / Future Considerations

### Horizontal Pod Autoscaler (HPA)

Currently all scaling is manual. HPA could automate pod scaling for Backend and Packager based on:
- CPU/memory utilization
- Custom metrics (e.g., Kafka consumer lag via Prometheus adapter)

**Status:** Deferred. To be evaluated once monitoring is fully operational and baseline traffic patterns are well understood.

### Cluster Autoscaler / Karpenter

Could automate EKS node scaling when pods can't schedule. Karpenter is the newer, AWS-native option that provisions right-sized nodes faster than Cluster Autoscaler.

**Status:** Deferred. Evaluate alongside HPA.

### Kafka Horizontal Scaling (Adding Brokers)

Adding a 4th+ broker is possible but involves:
1. Provisioning new EC2 instance
2. Running Ansible to configure the new broker
3. Updating `kafka_quorum_voters` across all brokers (rolling restart)
4. Reassigning partitions to the new broker (`kafka-reassign-partitions.sh`)
5. Waiting for data rebalancing to complete

This is a significant operation and should only be considered when vertical scaling is no longer viable.

**Status:** Not expected to be needed at current traffic levels. Document detailed procedure when approaching vertical scaling limits.

### CloudFormation Parameterization

The current `v4.yaml` has `DesiredSize`, `MinSize`, and `MaxSize` hardcoded in the template. Parameterizing these values would make node scaling simpler (parameter update instead of template edit).

**Status:** Recommended improvement for easier operational scaling.
