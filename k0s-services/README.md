# Kubernetes service templates

- `templates/<resource>.yaml.j2` is the source of truth for each Kubernetes resource.
- `private_cloud.<service>.*` and role-local Jinja expressions are the values substituted during deployment.
- Dataset paths and target nodes come from the owning Ansible service role.
- NodePorts, image references, and other repository-fixed Kubernetes values stay literal in the templates.
- `ansible/tasks/render_manifests.yml` renders the templates; each service role applies the resulting resources.
- The k0s release pin and checksum are repository values in `ansible/roles/k0s/defaults/main.yml`.
