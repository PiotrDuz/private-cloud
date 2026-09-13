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

The OpenVPN endpoint must be a literal IP address so its transport exception stays exact. The media role connects the applications through their native APIs after deployment.

[Jellyfin](../jellyfin/README.md) has its own templates and mounts the shared library read-only. The media role applies the arr stack and library storage before Jellyfin.

## Application configuration

- The installer reads Sonarr, Radarr, and Prowlarr API keys from their protected datasets.
- Prowlarr synchronizes selected indexers to Sonarr and Radarr.
- Sonarr and Radarr use qBittorrent with separate download categories.
- Sonarr uses `/media/tv` and Radarr uses `/media/movies` as library roots.
- Store `media.qbittorrent_password` in Vault and use `private-cloud` as the WebUI username.
- The startup initializer applies the qBittorrent password before its WebUI starts.
- Select indexer providers and provider credentials after deployment.
- The installer maintains the `private-cloud` quality profile from the configured Sonarr and Radarr preferences.
- The profile accepts standard HDTV, WEB, and Blu-ray qualities from 720p through the selected resolution.
- The profile excludes remux, raw, disc, and low-quality theatrical sources.
- The profile stops automatic upgrades at Blu-ray in the selected resolution.
- Select the `private-cloud` profile when adding series or movies and when configuring import lists.
- Managed connections use names beginning with `private-cloud-`.

Indexers provide searchable release listings; quality profiles specify acceptable formats, resolutions, and upgrade cutoffs.

The integration uses the native [Prowlarr application settings](https://github.com/Prowlarr/Prowlarr/blob/develop/src/NzbDrone.Core/Applications/Sonarr/SonarrSettings.cs) and [Sonarr qBittorrent settings](https://github.com/Sonarr/Sonarr/blob/develop/src/NzbDrone.Core/Download/Clients/QBittorrent/QBittorrentSettings.cs).

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

The installer seeds qBittorrent defaults and the startup initializer reapplies logging and WebUI credentials on every pod start. File logging rotates at 10MiB and removes logs after seven days. An existing configuration must use the documented path; forwarding remains best effort during abrupt crashes, rotation, and collector outages.

After deployment, browse the stream with:

```bash
sudo k0s kubectl logs -n media deployment/qbittorrent -c file-logs --follow
```
