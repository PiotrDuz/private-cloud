# Arr stack

The arr stack templates are managed by `ansible/roles/media` through the `media` installer stage.

- Configure `private_cloud.media` in the public configuration.
- Store OpenVPN credentials and the proxy password in the encrypted configuration.
- Deploy Sonarr, Radarr, Prowlarr, and qBittorrent in the `media` namespace.
- Route external traffic and DNS through the shared OpenVPN gateway.
- Use per-pod `tun2socks` helpers for the guarded applications.
- Block direct Internet fallback with NetworkPolicy.
- Bind qBittorrent to `tun0` and disable UPnP.
- Keep dashboards, peer ports, and discovery protocols unpublished.
- Give each application a quota-controlled dataset and a dedicated `10Ti` PV.
- Provision the shared `media-library` dataset and claim in this folder.
- Mount the shared library writable in Sonarr, Radarr, and qBittorrent.

The OpenVPN endpoint must be a literal IP address so its transport exception stays exact. Indexers, API keys, download clients, root folders, and quality profiles still require application setup after deployment.

[Jellyfin](../jellyfin/README.md) has its own templates and mounts the shared library read-only. The media role applies the arr stack and library storage before Jellyfin.

## File logs

The pinned qBittorrent 5.1.2 application logger has no native stdout configuration, so qBittorrent alone receives a logging sidecar. Its [application source](https://github.com/qbittorrent/qBittorrent/blob/release-5.1.2/src/app/application.cpp) configures the file logger separately from startup console output.

- Forward `/config/qBittorrent/logs/qbittorrent.log` through the `file-logs` sidecar.
- Emit JSON lines with `message`, `source_file`, and `collected_at` fields.
- Mount the source log directory read-only.
- Persist read positions under `.log-forwarder` in the qBittorrent dataset.
- Start the native sidecar before application containers and stop it after them.
- Use Recreate deployments to prevent overlapping checkpoint writers.
- Keep Sonarr, Radarr, and Prowlarr on their native console logging.

The configuration is [file-logs.conf](files/file-logs.conf). It discovers new files every second, follows renamed files for 30 seconds, and resumes saved offsets after a restart. First collection reads the current file from the beginning. Rotated backups are excluded from discovery to prevent replay.

Forwarding is best effort across abrupt crashes or rotation during an outage. Lines larger than 1 MiB are skipped with a Fluent Bit warning. Original application timestamps remain inside `message`; `collected_at` records collection time.

The installer seeds qBittorrent logging settings only when creating its configuration. It enables file logging, rotates at 10MiB, and removes logs after seven days. An existing configuration must use the documented path; forwarding remains best effort during abrupt crashes, rotation, and collector outages.

After deployment, browse the stream with:

```bash
sudo k0s kubectl logs -n media deployment/qbittorrent -c file-logs --follow
```
