# PLAN.md history review

Reviewed the reachable Git history of `PLAN.md` from its first recorded version, `97c985c`, through merge `09da3c5`, including both merge parents, `0a58395` and `96d5309`.
The review compares repository records; it does not establish deployed behavior or recover uncommitted or unreachable history.
Commit identifiers below can be inspected with `git show <commit>:PLAN.md` or `git show <commit> -- PLAN.md`.

## Information restored by this merge

The local commit `0a58395`, titled “PLAN md re-style”, changed requirements as well as formatting.
The remote numbered-list style is retained in the merge, with substantive content from both parents preserved.
Conflicting statements are recorded in PLAN section 24 instead of being silently discarded.

| Information | Local history | Merged location |
| --- | --- | --- |
| Container security rules | `0a58395` removed the entire security section, including fixed UIDs, user namespaces, capabilities, token automounting, Secret ownership, and Alloy privileges. | PLAN section 21 restores the remote requirements. |
| Detailed alerting contract | `0a58395` replaced specific alert rules with a general observation section. | PLAN sections 20 and 22 retain both specific and general requirements. |
| Alert timing and notification behavior | The removed material specified one-minute evaluations, five-minute windows and silence, heartbeat handling, Zabbix recoveries, hourly reminders, delivery retries, and maintenance behavior. | PLAN section 20 restores these details. |
| Monitoring boundaries | Remote `96d5309` explicitly removes OpenObserve application probes from Zabbix while retaining Alloy and certificate checks. | PLAN section 20 preserves this newer boundary. |
| Network precision | The restyle omitted explicit local-only Kubernetes and Zabbix ports, obsolete-port blocking, host services, namespace labels, callback routing, token separation, and the connection-matrix link. | PLAN section 16 restores those details. |
| ARR design additions | Local `0a58395` adds no-backup paths, per-service storage, the qBittorrent username, and explicit media-library placement. | PLAN section 17 retains these additions, with conflicting remote backup intent in section 24. |
| Remote configuration additions | Remote `96d5309` adds managed ARR profiles, detailed SMTP relay routing, and host collector diagnostics. | PLAN sections 4, 6, 17, and 19 preserve them. |
| Jellyfin metadata access | Local `39582c7` deliberately enables Internet metadata and image downloads. | PLAN sections 16 and 18 retain this change, with the older remote restriction recorded in section 24. |
| Operator work | Local `39582c7` splits operator setup from repository automation work. | TODO and SETUP retain that split, including remote quality-profile selection and new logging checks. |

## Older information still absent or abbreviated in PLAN.md

These omissions predate this merge.
Some requirements remain elsewhere in the repository; absence from PLAN does not by itself mean absence from the implementation.

| Information | Historical evidence | Present treatment | Assessment |
| --- | --- | --- | --- |
| Installer entrypoint and execution contract | `fe51e2a` and `9a47e72` require one Python entrypoint, one dependency-ordered playbook, create/update/reapply/rotation, full validation before host changes, and explicit pool-creation authorization. | `c93386c` removed the installation decisions section; [AGENTS.md](../AGENTS.md), [README.md](../README.md), and `ansible/install.py` retain the contract. | Missing from PLAN, preserved elsewhere. |
| Public YAML and Vault lifecycle | `9a47e72` explicitly separates public settings from Vault secrets and service-owned Secret templates. | PLAN retains role-owned Kubernetes Secrets and the plaintext restriction, but not the complete installer configuration lifecycle. | Abbreviated in PLAN. |
| Shared dataset catalog | `9a47e72` requires every enabled dataset in the shared catalog and Zabbix inventory. | PLAN mentions the enabled dataset catalog and dashboard; AGENTS documents `ansible/service_catalog.yml` ownership and validation. | The cross-cutting contract is less explicit in PLAN. |
| Meaning of backup classification | `9a47e72` says that `backup` is a classification, not an implemented schedule. | [TODO.md](../TODO.md) defers backup automation; [OPERATIONS.md](OPERATIONS.md#recovery) states that backup automation is absent. | Restore a short clarification if PLAN should stand alone. |
| Recovery design | `9a47e72` specifies independent copies, coordinated database/filesystem recovery points, off-host encryption and Vault recovery material, retention, backup frequency, recovery targets, and independent restore verification. | OPERATIONS preserves recovery-point consistency, off-host material, and restore checks; TODO defers recovery planning. | PLAN no longer contains the full recovery requirements or their explicit inventory. |
| Independent outage monitoring rationale | `9a47e72` explains that local mail cannot report complete host or mailbox outages until delivery recovers. | PLAN names dependencies; [SETUP.md](SETUP.md#monitoring) and OPERATIONS require independent monitoring. | The requirement survives elsewhere, but PLAN omits the full failure rationale. |
| Notification granularity | `9a47e72` distinguishes recognized alert instances from one email per raw log line and explains that per-line delivery requires a durable notification pipeline. | PLAN retains grouped severity rules and five-minute silence, without that explanatory boundary. | Readers can overinterpret the general “every Warning-or-higher” wording in section 22. |
| Notification retry and silence scope | `9a47e72` generally requires failed-notification retries, visible failures, and explicit operator maintenance silences. | PLAN gives concrete Zabbix retry and maintenance behavior and OpenObserve rule suppression. | The former general wording is narrower in the current plan. |
| Relay DNS changes | `9a47e72` explicitly instructs reapplying after relay address changes. | PLAN section 6 says SMTP policies use IPv4 addresses resolved when applied. | The policy mechanism survives, but the operator action is no longer explicit in PLAN. |
| Capacity versus retention | `9a47e72` explains that retention does not replace quota monitoring. | PLAN separately specifies retention and capacity alerts; OPERATIONS asks operators to check both. | The rationale was removed, while the mechanisms remain. |
| Implementation references | `fe51e2a` and `9a47e72` link Alloy collection/buffering and logging, alerting, and storage documentation. | Most reference links were removed by `c93386c`; the PostgreSQL tuning reference remains. | Useful historical research context, not additional target requirements. |

## Deliberately replaced designs

The following historical statements should not be restored as active requirements merely to make the file longer.
Their replacements are explicit in later commits.

| Earlier design | Replacement | Evidence |
| --- | --- | --- |
| `services-backed`, `services-no-backup`, and earlier `tank/secure/k0s/*` dataset names | Explicit `tank/secure/backup` and `tank/secure/no-backup` dataset trees | `1a952c0` |
| PostgreSQL shared buffers described as user maximum RAM plus 50% | 25% of the user-provided maximum container memory | `a401b84` |
| AFFiNE versioned migration Job and schema compatibility work | Fresh database preparation and greenfield operation | `caababe` and current AGENTS |
| Gmail mobile access through public IMAPS and SMTP submission | JMAP over HTTPS, SMTP forwarding on TCP 25, and unexposed 993/465/587 | `fe51e2a` |
| Loki and Grafana, TSDB v13, filesystem chunks, Grafana contact points, and Grafana-specific recovery/grouping rules | Alloy plus OpenObserve local storage and managed rules | `9a47e72` |
| Alerts on unclassified parsing failures and explicit per-failure ACME/SMTP/database/VPN rules | Recognized severity parsing, preserved unclassified messages, and Traefik 5xx classification | `9a47e72` |
| Backed-up OpenObserve state and explicit OpenObserve snapshot inclusion | Disposable OpenObserve state and log history under no-backup | `c93386c` |
| CPU limits alongside other logging resource limits | CPU requests and memory limits without CPU limits for Kubernetes containers | `c93386c` |
| Operator wiring of ARR clients, keys, and root folders | Automatic ARR API wiring, followed by managed quality profiles | `c93386c` and `96d5309` |
| Zabbix probes of OpenObserve health, search heartbeat, and internal warnings | OpenObserve missing-heartbeat rule, direct inspection, and independent monitoring | `96d5309` |
| Jellyfin with no initiated network traffic and all online integrations disabled | Direct metadata/image Internet access with remaining integration restrictions | `39582c7` |

## Related historical planning files

`ANSIBLE_MIGRATION_PLAN.md` at `d586716` contains additional installer details that were never all present in PLAN.
These include configuration locking, atomic writes, temporary secret cleanup, no prompts during Ansible execution, idempotent reruns, and supervised host upgrades.
The file was removed by `8a130ab`; its historical text is available with `git show d586716:ANSIBLE_MIGRATION_PLAN.md`.

`IMPLEMENTATION_PLAN.md` at `ce2df11` records past implementation reviews, static validation, rollout checks, host affinity, collector restrictions, and unresolved release-digest validation.
It was removed by `caababe`.
Those past validation results apply to that revision and do not certify the merged codebase.
Its schema-migration decisions also predate the current greenfield-only contract.

## Follow-up priorities

1. Reconcile ARR storage and DDNS ownership using the explicit alternatives preserved in PLAN section 24.
2. Restore a concise installer contract if PLAN must define the whole system independently.
3. Add a deferred backup and recovery section without reviving backed-up OpenObserve history.
4. Clarify that log alerts do not promise per-line emails or Zabbix-style recovery reminders.
5. Restore the relay-address reapply instruction in the operator documentation.
6. Keep historical replacements separate from active target requirements.

The static implementation comparison is recorded separately in [PLAN-IMPLEMENTATION-REVIEW.md](PLAN-IMPLEMENTATION-REVIEW.md).
