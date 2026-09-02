# Design review implementation

Focused implementation tasks use Codex agents with coordinator review before dependent work proceeds.

| Task | Scope | Dependencies | Status |
| --- | --- | --- | --- |
| 1 | Preflight, safe rotation guards, schema migration, installer diagnostics and Ansible configuration | None | Reviewed; migration and sanitized diagnostics are implemented |
| 2 | Optional dataset monitoring and restricted SMART execution | None | Reviewed; inventory, template filtering and wrapper checks pass |
| 3 | Reboot convergence, k0s version checks, rollout readiness and storage host affinity | None | Reviewed; static checks passed |
| 4 | Authoritative Tika YAML and deterministic non-secret rendering | 3 | Reviewed; six rendered resources pass strict schema validation |
| 5a | Authoritative PostgreSQL, Meilisearch, Bleve, OnlyOffice and Grist YAML | 4 | Reviewed; 30 rendered resources pass strict schemas |
| 5b | Authoritative Stalwart, OpenCloud, AFFiNE and Zabbix YAML | 2, 4 | Reviewed; 44 rendered resources pass strict schemas |
| 5c | Shared dataset/database operations and native configuration helpers | 5a, 5b | Reviewed; shared kubeconfig and dataset operations are extracted; database-role flows remain service-local because their SQL and credential transitions differ |
| 6a | Workload isolation, startup probes and resource budgets | 5 | Reviewed; egress approval is pending an operator decision |
| 6b | Deliberate upgrades, migration identity and Stalwart convergence | 5, 8 | Reviewed |
| 7a | Backup, recovery, networking and operating contracts | 1–3 | Reviewed; required site decisions remain explicit |
| 7b | Dependency compatibility, host capacity and release pinning | 1, 5 | Reviewed |
| 8 | Manticore service and supported AFFiNE integration | 1, 5b | Reviewed; six rendered resources pass strict schema validation |
| 9 | Integrated static validation and review reconciliation | All | Reviewed; all 11 examples render and 86 resources pass strict schema validation; Ansible syntax and production-profile lint pass |

Validation uses parsing, compilation, Ansible linting and Kubernetes schemas where available.
No tests, dry runs, installation or live infrastructure changes are authorized by this implementation plan.
External destinations and license choices require operator input.

## Review record

- Preflight assertion structure now passes direct static inspection.
- All public YAML files and Python sources parse.
- All 86 public Kubernetes resources render and pass strict schema validation.
- Ansible syntax and production-profile lint pass with the supplied collections.
- Focused repair removed incompatible collector arguments and temporary patch artifacts.
- ZFS version parsing checks userland and loaded kernel modules before pool changes.
- Readiness waits now require observed generation and ready updated replicas.
- Storage roles require the managed host node instead of selecting another Ready node.
- Reboot verification now continues through enabled service roles.
- Monitoring inventory installation and collector arguments now match.
- Dataset item filtering removes nested alerts for disabled services.
- SMART privileged access accepts only validated read-only command forms.
- Docker Hub digest resolution is blocked by TLS certificate validation in this environment.
