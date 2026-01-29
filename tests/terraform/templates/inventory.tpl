---
all:
  children:
    kafka:
      hosts:
%{ for idx, instance in instances ~}
        ${instance.hostname}:
          ansible_host: ${instance.main_ip}
          ansible_user: root
          kafka_node_id: ${idx + 1}
%{ endfor ~}
      vars:
        kafka_quorum_voters: "${quorum_voters}"
