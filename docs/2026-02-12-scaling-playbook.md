# Analytics Platform Scaling Playbook

## Purpose

This is the engineer's handbook for scaling the analytics pipeline. Find your scenario in the lookup table, jump to the section, follow the steps.

All scaling decisions are manual — based on engineer judgment from monitoring data. No auto-scaling is currently configured.

---

## Scaling Philosophy

| Component | Strategy | Rationale |
|---|---|---|
| **Kafka** | Over-provision for peak, scale vertically when outgrown | Adding/removing brokers requires partition rebalancing — a heavy operation. Simpler to size for peak. |
| **Backend (producer)** | Scale horizontally via pod replicas, then nodes | Spiky traffic hits the producer first. Pod scaling is fast (~seconds). Node scaling is slower (~minutes). |
| **Packager (consumer)** | Scale horizontally via pod replicas + partitions | Consumer parallelism is bounded by partition count. Scaling replicas beyond partition count has no effect. |

---

## Scenario Lookup Table

Find your situation, jump to the section.

| # | Scenario | You see in monitoring | Type | Section |
|---|---|---|---|---|
| 1 | Backend latency spiking | Request p99 > 500ms, pod CPU > 80% | Scaling | [S1](#s1-backend-latency-spiking) |
| 2 | Backend can't produce to Kafka | Produce errors, timeouts to brokers | Diagnosis | [S2](#s2-backend-cant-produce-to-kafka) |
| 3 | Backend pods crashing | OOM-killed, CrashLoopBackOff, frequent restarts | Diagnosis | [S3](#s3-backend-pods-crashing) |
| 4 | Preparing for traffic spike | Planned campaign or known peak event | Scaling | [S4](#s4-preparing-for-traffic-spike) |
| 5 | Consumer lag growing | Lag > 500K and increasing, Packager CPU high | Scaling | [S5](#s5-consumer-lag-growing) |
| 6 | Packager processing slowing | Lag growing but CPU is low, batch time increasing | Diagnosis | [S6](#s6-packager-processing-slowing-down) |
| 7 | S3 uploads failing | Consuming fine but Parquet files not appearing in S3 | Diagnosis | [S7](#s7-s3-uploads-failing) |
| 8 | Consumer rebalancing storms | Frequent rebalances, consumption stalls repeatedly | Diagnosis | [S8](#s8-consumer-rebalancing-storms) |
| 9 | Kafka disk filling up | Broker disk usage > 75% | Scaling | [S9](#s9-kafka-disk-filling-up) |
| 10 | Kafka broker overloaded | Network > 80%, request queue > 50, high CPU | Scaling | [S10](#s10-kafka-broker-overloaded) |
| 11 | Kafka JVM under pressure | Heap > 80%, GC pauses > 500ms | Scaling | [S11](#s11-kafka-jvm-under-pressure) |
| 12 | Pods can't schedule | Pods in Pending state, scheduling failures | Scaling | [S12](#s12-pods-cant-schedule) |

---

## Backend Scenarios

### S1: Backend Latency Spiking

**Symptoms:**

- Request latency p99 > 500ms
- Backend pod CPU > 80% sustained
- Backend pod memory > 85% sustained

**Diagnosis:**

```bash
kubectl top pods -n <namespace> -l app=backend
kubectl get deployment backend -n <namespace> -o wide
```

Confirm that Kafka produce latency is normal (< 50ms). If produce latency to Kafka is also high, the bottleneck may be Kafka — check [S10](#s10-kafka-broker-overloaded) first.

**Action — Scale Backend pods:**

```bash
kubectl scale deployment backend -n <namespace> --replicas=<N>
kubectl get pods -n <namespace> -l app=backend -w
```

Recommended replica counts:

| Traffic Level | Events/sec | Replicas |
|---|---|---|
| Low (off-peak) | < 5,000 | 2 |
| Normal | ~10,000 | 3-4 |
| High (peak) | 20,000-30,000 | 6-8 |
| Spike | > 30,000 | 10+ (ensure node capacity) |

If pods are Pending after scaling, see [S12](#s12-pods-cant-schedule).

**Verify:**

- Request latency p99 returns to < 100ms
- Pod CPU drops below 60%
- No produce errors to Kafka

---

### S2: Backend Can't Produce to Kafka

**Symptoms:**

- Kafka produce errors in Backend logs
- Produce timeouts or connection refused
- Backend request latency may or may not be high

**Diagnosis:**

This is typically **not a scaling issue**. Check in order:

```bash
# 1. Can Backend pods reach Kafka brokers?
kubectl exec -it <backend-pod> -n <namespace> -- \
  nc -zv <kafka-broker-ip> 9092

# 2. Are all Kafka brokers running?
ssh <broker> systemctl status kafka

# 3. Are there under-replicated partitions?
ssh <broker> /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --describe --under-replicated-partitions
```

**Decision:**

| Condition | Action |
|---|---|
| Network unreachable | Check security groups, VPC routing — not scaling |
| Kafka broker is down | Restart broker, investigate root cause |
| Under-replicated partitions | Broker health issue — see [S10](#s10-kafka-broker-overloaded) or [S11](#s11-kafka-jvm-under-pressure) |
| Kafka disk full | See [S9](#s9-kafka-disk-filling-up) |
| All checks pass | Check Backend application logs for misconfiguration (wrong broker address, auth issues) |

**Verify:**

- Produce errors stop
- Messages flowing through pipeline (check consumer lag is not growing)

---

### S3: Backend Pods Crashing

**Symptoms:**

- Pods in CrashLoopBackOff or frequent restarts
- OOMKilled events in pod description
- Restart count increasing

**Diagnosis:**

```bash
# Check pod events and exit reason
kubectl describe pod <backend-pod> -n <namespace>
# Look for: OOMKilled, Error, Liveness probe failed

# Check recent logs from crashed pod
kubectl logs <backend-pod> -n <namespace> --previous
```

**Decision:**

| Condition | Action |
|---|---|
| OOMKilled | Increase memory limits in deployment spec, or reduce per-pod load by scaling replicas |
| Application error in logs | Not a scaling issue — fix the application bug |
| Liveness probe timeout | Pod is overloaded — scale replicas (see [S1](#s1-backend-latency-spiking)), or increase probe timeout |

**Verify:**

- Pod restart count stabilizes
- No OOMKilled events
- Request latency normal

---

### S4: Preparing for Traffic Spike

**Symptoms:**

- No current issue — this is proactive scaling before a planned event (campaign launch, marketing push, seasonal peak)

**Pre-scale checklist:**

**1. Scale Backend pods:**

```bash
# Scale to high/spike level before the event
kubectl scale deployment backend -n <namespace> --replicas=<N>
kubectl get pods -n <namespace> -l app=backend -w
```

**2. Scale Packager pods (up to partition count):**

```bash
# Check partition count first
ssh <broker> /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 --topic <topic> --describe

# Scale to match (do not exceed partition count)
kubectl scale deployment packager -n <namespace> --replicas=<N>
```

**3. Verify EKS node capacity:**

```bash
# Check if all pods are Running (not Pending)
kubectl get pods -A --field-selector=status.phase=Pending

# If pods are Pending, scale nodes first — see S12
```

**4. Verify Kafka cluster health:**

```bash
ssh <broker> /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 --describe --under-replicated-partitions
# Must return empty — all partitions in-sync before the event
```

**5. Check Kafka disk headroom:**

```bash
ssh <broker> df -h /data/kafka
# Ensure > 40% free. If not, see S9 before the event
```

**After the event — scale down:**

```bash
kubectl scale deployment backend -n <namespace> --replicas=<normal-count>
kubectl scale deployment packager -n <namespace> --replicas=<normal-count>
```

---

## Packager Scenarios

### S5: Consumer Lag Growing

**Symptoms:**

- Consumer lag > 500,000 messages and increasing
- Packager pod CPU > 80%
- Parquet files arriving late to S3

**Diagnosis:**

```bash
# Check current lag per partition
ssh <broker> /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server <broker>:9092 \
  --group <packager-consumer-group> --describe

# Check current Packager replicas vs partition count
kubectl get deployment packager -n <namespace>
ssh <broker> /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 --topic <topic> --describe
```

**Decision:**

| Condition | Action |
|---|---|
| Replicas < partition count and CPU is high | Scale Packager pods |
| Replicas = partition count and CPU is high | Add partitions first ([Appendix C](#appendix-c-adding-kafka-partitions)), then scale pods |
| CPU is low but lag grows | Not a scaling issue — see [S6](#s6-packager-processing-slowing-down) |

**Action — Scale Packager pods:**

```bash
kubectl scale deployment packager -n <namespace> --replicas=<N>
```

**Verify:**

- Consumer lag is decreasing (watch over 5-10 minutes)
- Packager pod CPU returns to normal range
- Parquet files resuming in S3

---

### S6: Packager Processing Slowing Down

**Symptoms:**

- Consumer lag growing
- Packager pod CPU is **low** (< 50%) — pods are not resource-starved
- Batch processing time or enrichment duration increasing
- Fewer Parquet files produced per unit time

**Diagnosis:**

This is typically **not a scaling issue** — adding more replicas won't help if each pod is slow.

```bash
# Check Packager application logs for slow operations
kubectl logs <packager-pod> -n <namespace> --tail=100

# Check if enrichment depends on an external service
# (database query, API call) that is slow
kubectl exec -it <packager-pod> -n <namespace> -- \
  curl -w "%{time_total}\n" -o /dev/null -s <enrichment-service-url>
```

**Decision:**

| Condition | Action |
|---|---|
| External service (DB, API) is slow | Fix the external dependency — not a Packager scaling issue |
| Data volume per record increased | Application-level optimization needed |
| S3 uploads slow | See [S7](#s7-s3-uploads-failing) |
| No obvious cause | Profile the application, check for memory pressure or GC issues in Packager |

**Verify:**

- Batch processing time returns to baseline
- Consumer lag decreasing

---

### S7: S3 Uploads Failing

**Symptoms:**

- Packager consuming messages fine (lag not growing due to consumption speed)
- Parquet files not appearing in S3
- S3 errors in Packager logs

**Diagnosis:**

This is **not a scaling issue**.

```bash
# Check Packager logs for S3 errors
kubectl logs <packager-pod> -n <namespace> --tail=100 | grep -i "s3\|upload\|error"

# Test S3 connectivity from the pod
kubectl exec -it <packager-pod> -n <namespace> -- \
  aws s3 ls s3://<bucket-name>/ --region ap-southeast-1
```

**Decision:**

| Condition | Action |
|---|---|
| Access denied / 403 | Check IAM role attached to EKS node group, verify S3 bucket policy |
| S3 throttling / 503 SlowDown | Implement exponential backoff, use S3 prefixes to distribute load |
| Network timeout | Check NAT gateway health, VPC endpoint for S3 may help |
| Bucket doesn't exist | Check application configuration |

**Verify:**

- S3 upload errors stop in Packager logs
- Parquet files appearing in S3

---

### S8: Consumer Rebalancing Storms

**Symptoms:**

- Frequent consumer group rebalances in Packager logs
- Consumption stalls repeatedly (lag grows in bursts)
- Packager pods themselves are healthy (not crashing)

**Diagnosis:**

This is typically **not a scaling issue**. Rebalancing storms happen when consumers repeatedly join/leave the group.

```bash
# Check Packager logs for rebalance events
kubectl logs <packager-pod> -n <namespace> --tail=200 | grep -i "rebalanc"

# Check if pods are restarting frequently
kubectl get pods -n <namespace> -l app=packager -w

# Check consumer group state
ssh <broker> /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server <broker>:9092 \
  --group <packager-consumer-group> --describe
```

**Decision:**

| Condition | Action |
|---|---|
| Pods restarting (OOMKilled, crashes) | Fix the crash first — see [S3](#s3-backend-pods-crashing) (same approach for Packager) |
| Processing takes longer than `max.poll.interval.ms` | Increase `max.poll.interval.ms` in consumer config, or reduce `max.poll.records` |
| Scaling up/down during rebalance | Wait for rebalance to complete before scaling again |
| Deploying new version | Expected during rollout — wait for stabilization |

**Verify:**

- No rebalance events in logs for 10+ minutes
- Consumer lag is steadily decreasing
- All partitions assigned in consumer group describe output

---

## Kafka Scenarios

### S9: Kafka Disk Filling Up

**Symptoms:**

- Broker disk usage > 75%
- Disk usage trending upward

**Diagnosis:**

```bash
ssh <broker> df -h /data/kafka

# Check which topics consume the most space
ssh <broker> du -sh /data/kafka/* | sort -rh | head -10
```

**Decision:**

| Condition | Action |
|---|---|
| Gradual growth, approaching capacity | Expand EBS volume ([Appendix D](#appendix-d-ebs-disk-expansion)) |
| Sudden spike from one topic | Reduce retention on that topic (see below) |
| Consumer lag caused data to pile up | Fix the consumer issue first ([S5](#s5-consumer-lag-growing)), then expand disk if needed |

**Action — Reduce retention (temporary relief):**

```bash
# Reduce retention to 48 hours (from default 72)
ssh <broker> /opt/kafka/bin/kafka-configs.sh \
  --bootstrap-server <broker>:9092 \
  --alter --entity-type topics --entity-name <topic-name> \
  --add-config retention.ms=172800000
```

For permanent fix, expand the disk: [Appendix D](#appendix-d-ebs-disk-expansion).

**Verify:**

- Disk usage below 75%
- Disk usage trend stabilizing or decreasing

---

### S10: Kafka Broker Overloaded

**Symptoms:**

- Network throughput > 80% of instance capacity
- Request queue size > 50 sustained
- High broker CPU utilization
- Produce/fetch latency increasing

**Diagnosis:**

```bash
# Check under-replicated partitions
ssh <broker> /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --describe --under-replicated-partitions

# Check leader distribution — is one broker handling too many leaders?
ssh <broker> /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --describe | awk -F'\t' '/Leader:/ {print $4}' | sort | uniq -c | sort -rn
```

**Decision:**

| Condition | Action |
|---|---|
| Leaders skewed to one broker | Trigger preferred leader election (see below) |
| All brokers equally loaded, at capacity | Vertical scale — [Appendix A](#appendix-a-rolling-broker-restart-vertical-scale) |
| Single broker down, others overloaded | Restart the failed broker, investigate root cause |

**Action — Rebalance leaders (if skewed):**

```bash
ssh <broker> /opt/kafka/bin/kafka-leader-election.sh \
  --bootstrap-server <broker>:9092 \
  --election-type preferred \
  --all-topic-partitions
```

If the cluster is at capacity even with balanced leaders, vertical scale is needed: [Appendix A](#appendix-a-rolling-broker-restart-vertical-scale).

**Verify:**

- Network throughput below 60%
- Request queue below 10
- Leader count evenly distributed across brokers

---

### S11: Kafka JVM Under Pressure

**Symptoms:**

- JVM heap usage > 80% sustained
- GC pause time > 500ms
- Broker appears sluggish or unresponsive during GC pauses

**Diagnosis:**

Check if this is a heap configuration issue or an instance capacity issue:

```bash
# Check current heap settings
ssh <broker> grep KAFKA_HEAP_OPTS /etc/systemd/system/kafka.service

# Check actual memory available
ssh <broker> free -m
```

**Decision:**

| Condition | Action |
|---|---|
| Heap < 25% of RAM (misconfigured) | Increase heap in kafka.service, restart broker |
| Heap already at max (8GB), RAM is small | Vertical scale — [Appendix A](#appendix-a-rolling-broker-restart-vertical-scale) |
| Heap at 8GB, plenty of RAM | May need to tune beyond the 8GB cap — override `kafka_heap_size` in Ansible group_vars |

**Action — Increase heap (single broker, no instance change):**

```bash
ssh <broker>

# Edit heap setting
sudo vi /etc/systemd/system/kafka.service
# Update: Environment="KAFKA_HEAP_OPTS=-Xms<new>m -Xmx<new>m"

# Restart
sudo systemctl daemon-reload
sudo systemctl restart kafka
```

> **Warning:** Restarting a broker causes a brief leader re-election. Do this during low-traffic periods. If changing all brokers, use the rolling restart procedure: [Appendix A](#appendix-a-rolling-broker-restart-vertical-scale).

**Verify:**

- JVM heap usage < 70%
- GC pauses < 100ms
- No under-replicated partitions after restart

---

## EKS Infrastructure Scenarios

### S12: Pods Can't Schedule

**Symptoms:**

- Pods stuck in Pending state
- `kubectl describe pod` shows "Insufficient cpu" or "Insufficient memory"
- Scaling pods doesn't help because they can't be placed

**Diagnosis:**

```bash
# Find pending pods
kubectl get pods -A --field-selector=status.phase=Pending

# Check why they can't schedule
kubectl describe pod <pending-pod> -n <namespace>
# Look for Events: "Insufficient cpu", "Insufficient memory",
# "0/2 nodes are available"

# Check current node utilization
kubectl top nodes
```

**Decision:**

| Condition | Action |
|---|---|
| Nodes at capacity, pods need more room | Scale EKS node group — [Appendix B](#appendix-b-eks-node-scaling-via-cloudformation) |
| Pod requests too large for any node | Reduce pod resource requests, or use larger instance type |
| Node is NotReady | Investigate node health (EC2 status checks, kubelet logs) — not a scaling issue |

**Verify:**

- No pods in Pending state
- New node shows Ready status
- All pods Running

---

## Appendix A: Rolling Broker Restart (Vertical Scale)

Use this procedure for any operation that requires restarting Kafka brokers: instance type upgrade, heap changes across all brokers, or configuration changes.

### Pre-requisites

- Kafka cluster has replication factor >= 2 (production: 3)
- Min in-sync replicas allows one broker to be offline (production: 2 of 3)

### Resource-Dependent Configuration

After changing instance type, these Kafka parameters must be recalculated:

| Parameter | Config File | Formula |
|---|---|---|
| `kafka_heap_size` | `/etc/systemd/system/kafka.service` | 25% of RAM (min 1GB, max 8GB) |
| `kafka_num_network_threads` | `/etc/kafka/server.properties` | vCPU / 2 (min 1, max 3) |
| `kafka_num_io_threads` | `/etc/kafka/server.properties` | vCPU * 2 (min 4, max 8) |

> **Note:** With current caps (8GB heap, 3 network threads, 8 IO threads), scaling beyond 16 vCPU / 32GB RAM will not change these values. Override in Ansible `group_vars` if you need to tune beyond caps.

Source: `roles/kafka/defaults/main.yml` lines 46-48.

### Procedure

> **Critical:** Never upgrade more than one broker simultaneously. The cluster must be fully healthy before moving to the next broker.

```
Broker 1: stop → resize → reconfigure → start → wait for sync → verify leader spread
                                                                        |
                                                              All healthy? ──No──> STOP. Investigate.
                                                                        |
                                                                       Yes
                                                                        v
Broker 2: stop → resize → reconfigure → start → wait for sync → verify leader spread
                                                                        |
                                                              All healthy? ──No──> STOP. Investigate.
                                                                        |
                                                                       Yes
                                                                        v
Broker 3: stop → resize → reconfigure → start → wait for sync → verify leader spread ──> Done
```

**Repeat the following steps for each broker, one at a time:**

**Step 1: Check cluster health before starting**

```bash
# Under-replicated partitions must be zero
ssh <broker> /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --describe --under-replicated-partitions
# Expected: no output

# Leader distribution must be balanced
ssh <broker> /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --describe | awk -F'\t' '/Leader:/ {print $4}' | sort | uniq -c | sort -rn
```

Also confirm in monitoring:
- No under-replicated partitions
- Leader count balanced across brokers
- No active producer errors from Backend
- Consumer lag stable (not growing)

> **Do not proceed if the cluster is not fully healthy.**

**Step 2: Gracefully stop Kafka**

```bash
ssh <broker> sudo systemctl stop kafka
```

After stopping, leaders will be reassigned to remaining brokers. Monitor:
- Under-replicated partitions will temporarily appear (expected)
- Leader re-election completes
- Producer/consumer traffic continues on remaining brokers

**Step 3: Stop the EC2 instance**

```bash
aws ec2 stop-instances --instance-ids <instance-id>
aws ec2 wait instance-stopped --instance-ids <instance-id>
```

**Step 4: Change instance type**

```bash
aws ec2 modify-instance-attribute \
  --instance-id <instance-id> \
  --instance-type <new-type>
```

**Step 5: Start the EC2 instance**

```bash
aws ec2 start-instances --instance-ids <instance-id>
aws ec2 wait instance-running --instance-ids <instance-id>
```

**Step 6: Reconfigure Kafka for new resources**

SSH to the broker and update configuration files.

**6a.** Calculate new values:

```bash
nproc                    # vCPU count
free -m | grep Mem       # Total memory in MB

# heap_size       = min(RAM_MB * 0.25, 8192), minimum 1024
# network_threads = max(vCPU / 2, 1), capped at 3
# io_threads      = max(vCPU * 2, 4), capped at 8
```

**6b.** Update `/etc/kafka/server.properties`:

```bash
sudo vi /etc/kafka/server.properties
# num.network.threads=<new_value>
# num.io.threads=<new_value>
```

**6c.** Update `/etc/systemd/system/kafka.service`:

```bash
sudo vi /etc/systemd/system/kafka.service
# Environment="KAFKA_HEAP_OPTS=-Xms<new_heap>m -Xmx<new_heap>m"
```

**6d.** Reload systemd and start Kafka:

```bash
sudo systemctl daemon-reload
sudo systemctl start kafka
```

**Step 7: Wait for broker to fully rejoin and sync**

```bash
watch -n 5 'ssh <broker> /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --describe --under-replicated-partitions'
# Wait until output is empty — all partitions in-sync
```

> **Do not proceed to the next broker until this returns zero results.** This may take minutes to hours depending on data volume.

**Step 8: Verify leader spread is balanced**

```bash
ssh <broker> /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --describe | awk -F'\t' '/Leader:/ {print $4}' | sort | uniq -c | sort -rn
```

If leaders are skewed, trigger a preferred leader election:

```bash
ssh <broker> /opt/kafka/bin/kafka-leader-election.sh \
  --bootstrap-server <broker>:9092 \
  --election-type preferred \
  --all-topic-partitions
```

Confirm in monitoring:
- Under-replicated partitions = 0
- Leader count balanced
- Producer error rate = 0
- Consumer lag stable or decreasing

> **Only proceed to the next broker when all checks pass.**

**Step 9: Move to the next broker**

Repeat Steps 1-8. For a 3-node cluster, the full rolling upgrade requires 3 iterations.

---

## Appendix B: EKS Node Scaling via CloudFormation

> **Note:** The current CloudFormation template (`v4.yaml`) has `DesiredSize`, `MinSize`, and `MaxSize` hardcoded. To change node counts, update the template directly and run a stack update.

**Step 1: Update the CloudFormation template**

Edit `v4.yaml` and change the `ScalingConfig` for the target node group:

```yaml
ScalingConfig:
  DesiredSize: <new-desired>
  MaxSize: <new-max>
  MinSize: <new-min>
```

**Step 2: Update the stack**

```bash
aws cloudformation update-stack \
  --stack-name <stack-name> \
  --template-body file://v4.yaml \
  --capabilities CAPABILITY_NAMED_IAM
```

**Step 3: Wait for new nodes to join**

```bash
kubectl get nodes -w
# Wait for new node to show Ready status
```

**Step 4: Verify pods are scheduled**

```bash
kubectl get pods -A --field-selector=status.phase=Pending
# Should return no results
```

To change **instance type** instead of count, update the `NodeGroupInstanceTypes` parameter:

```bash
aws cloudformation update-stack \
  --stack-name <stack-name> \
  --use-previous-template \
  --parameters \
    ParameterKey=NodeGroupInstanceTypes,ParameterValue=<new-type> \
    ParameterKey=VPCCidrBlock,UsePreviousValue=true \
    ParameterKey=PublicCidrBlock1,UsePreviousValue=true \
    ParameterKey=PublicCidrBlock2,UsePreviousValue=true \
    ParameterKey=PrivateCidrBlock1,UsePreviousValue=true \
    ParameterKey=PrivateCidrBlock2,UsePreviousValue=true \
    ParameterKey=EKSClusterVersion,UsePreviousValue=true \
    ParameterKey=EfsEnable,UsePreviousValue=true \
  --capabilities CAPABILITY_NAMED_IAM
```

---

## Appendix C: Adding Kafka Partitions

> **Important:** Partitions can be increased but **never decreased**. Plan partition counts carefully.

> **Warning:** Adding partitions to a topic with key-based partitioning will change the partition assignment for keys. If the Packager relies on key ordering, coordinate this change carefully.

**Step 1: Check current partition count**

```bash
ssh <broker> /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --topic <topic-name> --describe
```

**Step 2: Increase partition count**

```bash
ssh <broker> /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --topic <topic-name> --alter \
  --partitions <new-count>
```

**Step 3: Scale Packager replicas to match**

```bash
kubectl scale deployment packager -n <namespace> --replicas=<new-count>
```

**Step 4: Verify even distribution**

```bash
ssh <broker> /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server <broker>:9092 \
  --topic <topic-name> --describe
# Check partition leaders are distributed across all brokers
```

**Guidelines:**

| Events/sec | Suggested Partitions | Max Packager Replicas |
|---|---|---|
| < 10,000 | 10 | 10 |
| 10,000-30,000 | 20-30 | 20-30 |
| 30,000-100,000 | 50 | 50 |
| > 100,000 | 100+ (test first) | 100+ |

---

## Appendix D: EBS Disk Expansion

This is a non-disruptive, online operation. No Kafka downtime required.

**Step 1: Identify the EBS volume**

```bash
aws ec2 describe-instances \
  --instance-ids <instance-id> \
  --query 'Reservations[].Instances[].BlockDeviceMappings[]'
```

**Step 2: Resize the volume**

```bash
aws ec2 modify-volume \
  --volume-id <volume-id> \
  --size <new-size-gb>

# Wait for modification to complete
aws ec2 describe-volumes-modifications \
  --volume-ids <volume-id>
# Wait until State is "completed" or "optimizing"
```

**Step 3: Expand the partition on the broker**

```bash
ssh <broker>

# Identify the device and partition (e.g., /dev/nvme1n1p1 or /dev/xvdf1)
lsblk

# Grow the partition to use the new space
sudo growpart /dev/<device> <partition-number>
# Example: sudo growpart /dev/nvme1n1 1
```

**Step 4: Extend the filesystem**

```bash
sudo xfs_growfs /data/kafka
```

**Step 5: Verify new size**

```bash
df -h /data/kafka
```

---

## Pending / Future Considerations

### Horizontal Pod Autoscaler (HPA)

Currently all scaling is manual. HPA could automate pod scaling for Backend and Packager based on CPU/memory utilization or custom metrics (e.g., Kafka consumer lag via Prometheus adapter).

**Status:** Deferred. To be evaluated once monitoring is fully operational and baseline traffic patterns are well understood.

### Cluster Autoscaler / Karpenter

Could automate EKS node scaling when pods can't schedule. Karpenter is the newer, AWS-native option that provisions right-sized nodes faster than Cluster Autoscaler.

**Status:** Deferred. Evaluate alongside HPA.

### Kafka Horizontal Scaling (Adding Brokers)

Adding a 4th+ broker is possible but involves provisioning a new EC2 instance, running Ansible, updating `kafka_quorum_voters` across all brokers (rolling restart), reassigning partitions, and waiting for data rebalancing.

**Status:** Not expected to be needed at current traffic levels. Document detailed procedure when approaching vertical scaling limits.

### CloudFormation Parameterization

The current `v4.yaml` has `DesiredSize`, `MinSize`, and `MaxSize` hardcoded. Parameterizing these values would make node scaling simpler (parameter update instead of template edit).

**Status:** Recommended improvement for easier operational scaling.
