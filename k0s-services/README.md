# Kubernetes service templates

- `templates/<resource>.yaml.j2` is the source of truth for each Kubernetes resource.
- `private_cloud.<service>.*` and role-local Jinja expressions are the values substituted during deployment.
- Dataset paths and target nodes come from the owning Ansible service role.
- NodePorts, image references, and other repository-fixed Kubernetes values stay literal in the templates.
- `ansible/tasks/render_manifests.yml` renders the templates; each service role applies the resulting resources.
- The k0s release pin and checksum are repository values in `ansible/roles/k0s/defaults/main.yml`.

## Runtime security

- Application containers run with fixed non-root UIDs and disabled privilege escalation.
- Linux capabilities are dropped unless a workload documents a required capability.
- Zabbix server retains `NET_RAW` for ICMP checks.
- Ansible aligns persistent dataset ownership with each workload UID and GID.
- AFFiNE and OnlyOffice retain UID 0 inside Kubernetes user namespaces.
- User-namespaced root maps to an unprivileged and pod-specific host UID.
- Stateful user namespaces require Linux 6.3+, OpenZFS 2.2+, and containerd 2.0+.
