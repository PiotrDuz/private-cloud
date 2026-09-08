# k0s service contributor guidelines

- Keep Kubernetes resource definitions in `templates/*.yaml.j2`.
- Render templates directly through the owning Ansible role.
- Use Jinja only for user configuration or repository-managed Ansible values.
- Do not add Kustomize bases, overlays, or Python manifest overrides.
- Keep public configuration and encrypted secrets separate.
- Prefer ClusterIP services behind the shared Traefik edge.
- Keep an approved NodePort literal in its owning service template.
- Keep the k0s release version and checksum in `ansible/roles/k0s/defaults/main.yml`.
- Keep Zabbix host settings in `ansible/service_catalog.yml`.
- This greenfield project has no configuration migrations or compatibility paths.
- Give every persistent service a dataset under `backup/k0s/services` by default.
- Use `no-backup/k0s/services` only when the service data is disposable.
- Give every service dataset a quota.
- Keep every persistent service PV and PVC at `10Ti`.
- Do not emit Kubernetes Secret resources from public manifest templates.
