# Single Node Kafka Testing Guide

Step-by-step guide to deploy and test Kafka on a single VM from your local machine.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) - Python package manager
- [task](https://taskfile.dev/) - Task runner
- [terraform](https://www.terraform.io/) - Infrastructure provisioning
- Vultr API key exported as `VULTR_API_KEY`

## 1. Create Single VM

Scale down to 1 instance and apply:

```bash
cd terraform
terraform apply -var="instance_count=1" -auto-approve
```

Note the IP address from the output.

## 2. Wait for SSH

```bash
task test:wait-for-ssh
```

## 3. Verify Connectivity

```bash
task ansible:ping
```

## 4. Deploy Kafka

```bash
# Deploy to kafka-test-1 (default)
task ansible:deploy:single

# Or specify a target VM
task ansible:deploy:single -- kafka-test-2
```

## 5. Verify Deployment

```bash
task ansible:verify
```

## 6. Manual Testing (Optional)

SSH into the VM:

```bash
task infra:ssh -- kafka-test-1
```

Create a test topic:

```bash
/opt/kafka/bin/kafka-topics.sh --create --topic test --bootstrap-server localhost:9092
```

List topics:

```bash
/opt/kafka/bin/kafka-topics.sh --list --bootstrap-server localhost:9092
```

Produce a message:

```bash
echo "hello kafka" | /opt/kafka/bin/kafka-console-producer.sh --topic test --bootstrap-server localhost:9092
```

Consume the message:

```bash
/opt/kafka/bin/kafka-console-consumer.sh --topic test --from-beginning --bootstrap-server localhost:9092 --max-messages 1
```

Exit SSH with `exit`.

## 7. Cleanup

Destroy the VM:

```bash
task infra:down
```

## Quick Reference

| Command | Description |
|---------|-------------|
| `task ansible:ping` | Test connectivity |
| `task ansible:deploy:single -- kafka-test-N` | Deploy Kafka to single VM |
| `task ansible:deploy` | Deploy Kafka to all VMs |
| `task ansible:verify` | Run verification playbook |
| `task infra:status` | Show VM IPs |
| `task infra:ssh -- kafka-test-1` | SSH into VM |
| `task infra:down` | Destroy VMs |
