# Manual Single Node Kafka Deployment

Test VM: `45.76.153.107`

## 1. SSH into the VM

```bash
ssh root@45.76.153.107
```

## 2. Install Java

```bash
apt update && apt install -y openjdk-21-jdk
```

## 3. Verify Java

```bash
java -version
```

## 4. Create kafka user

```bash
groupadd kafka
useradd -r -g kafka -s /sbin/nologin kafka
```

## 5. Create directories

```bash
mkdir -p /opt/kafka /data/kafka /var/log/kafka /etc/kafka
chown -R kafka:kafka /data/kafka /var/log/kafka /etc/kafka
```

## 6. Download and extract Kafka

```bash
cd /tmp
wget https://downloads.apache.org/kafka/4.1.1/kafka_2.13-4.1.1.tgz
tar -xzf kafka_2.13-4.1.1.tgz -C /opt/kafka --strip-components=1
chown -R kafka:kafka /opt/kafka
```

## 7. Generate cluster ID

```bash
CLUSTER_ID=$(/opt/kafka/bin/kafka-storage.sh random-uuid)
echo $CLUSTER_ID
```

## 8. Create server.properties

```bash
cat > /etc/kafka/server.properties << 'EOF'
node.id=1
process.roles=broker,controller
listeners=PLAINTEXT://:9092,CONTROLLER://:9093
advertised.listeners=PLAINTEXT://45.76.153.107:9092
controller.listener.names=CONTROLLER
controller.quorum.voters=1@localhost:9093
log.dirs=/data/kafka
num.partitions=1
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
EOF
```

## 9. Format storage

```bash
/opt/kafka/bin/kafka-storage.sh format -t $CLUSTER_ID -c /etc/kafka/server.properties
```

## 10. Start Kafka (foreground)

```bash
/opt/kafka/bin/kafka-server-start.sh /etc/kafka/server.properties
```

---

## Testing (in another terminal)

Open a new terminal and SSH again:

```bash
ssh root@45.76.153.107
```

### Create topic

```bash
/opt/kafka/bin/kafka-topics.sh --create --topic test --bootstrap-server localhost:9092
```

### List topics

```bash
/opt/kafka/bin/kafka-topics.sh --list --bootstrap-server localhost:9092
```

### Produce message

```bash
echo "hello kafka" | /opt/kafka/bin/kafka-console-producer.sh --topic test --bootstrap-server localhost:9092
```

### Consume message

```bash
/opt/kafka/bin/kafka-console-consumer.sh --topic test --from-beginning --bootstrap-server localhost:9092 --max-messages 1
```

---

## Cleanup

Stop Kafka with `Ctrl+C` in the first terminal.
