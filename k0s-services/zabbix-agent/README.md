# Zabbix Agent Kubernetes access

The Kubernetes access of the host Zabbix Agent is managed by `ansible/roles/zabbix_agent`.

- The `zabbix-agent` ServiceAccount in `private-cloud` identifies the host workload collector.
- Its ClusterRole only lists pods and pod metrics from the k0s metrics-server.
- The role creates the long-lived token Secret outside the public templates.
- The agent host keeps the API address, CA, and token in a file readable only by root and the `zabbix` group.
- No pod runs for this access; the collector runs on the host.

## Manifest review

- Ansible renders the `templates/*.yaml.j2` files during deployment.
