# Contributing

- Keep documentation bullets short and limited to one sentence.
- Use Python for repository scripts.
- Keep script entry points procedural and place helpers below the main flow.
- Move shared helpers to a top-level helper module.
- Avoid usage banners and excessive output in scripts.
- Do not add dry-run behavior.
- Do not add tests unless the repository policy changes.
- Give each Kubernetes service its own quota-limited dataset.
- Place service data under `tank/secure/backup/k0s/services` by default.
- Use `tank/secure/no-backup/k0s/services` only for explicitly disposable data.
- Keep each service PV capacity at `10Ti` and enforce actual use with its ZFS quota.
- Preserve unrelated working-tree changes.
- Document operator actions separately from implemented automation.
- Do not include secrets, real domains, account identifiers, or backup endpoints.

No repository license has been selected.

Record a license decision before accepting or redistributing contributions.
