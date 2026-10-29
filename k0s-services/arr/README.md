# Arr stack

The arr stack templates are managed by `ansible/roles/media` through the `media` installer stage.

- The installer reads `private_cloud.media` from the public configuration.
- The encrypted configuration holds the AirVPN WireGuard keys and the proxy password.
- Sonarr, Radarr, Prowlarr, and qBittorrent run in the `media` namespace.
- External traffic and DNS go through the shared AirVPN WireGuard gateway.
- Per-pod `tun2socks` helpers carry the guarded applications' traffic.
- NetworkPolicy blocks direct Internet fallback.
- qBittorrent binds to `tun0` with UPnP disabled.
- Dashboards, peer ports, and discovery protocols stay unpublished.
- The arr stack and shared library use `no-backup` datasets.
- Each application has a quota-controlled dataset and a dedicated `10Ti` PV.
- This folder provisions the shared `media-library` dataset and claim.
- Sonarr, Radarr, and qBittorrent mount the shared library writable.

Gluetun selects an AirVPN server by configured country from its built-in list, so no DNS lookup leaves the tunnel. AirVPN port forwarding cannot reach qBittorrent through the shadowsocks and `tun2socks` path, so qBittorrent stays unreachable for inbound peers. The media role connects the applications through their native APIs after deployment.

[Jellyfin](../jellyfin/README.md) has its own templates and mounts the shared library read-only. The media role applies the arr stack and library storage before Jellyfin.

## Application configuration

- The installer reads Sonarr, Radarr, and Prowlarr API keys from their protected datasets.
- Prowlarr synchronizes selected indexers to Sonarr and Radarr.
- Sonarr and Radarr use qBittorrent with separate download categories.
- qBittorrent stops each torrent at share ratio 0, so it seeds only while downloading.
- Sonarr and Radarr remove stopped torrents and their download copies after import.
- Sonarr uses `/media/tv` and Radarr uses `/media/movies` as library roots.
- The encrypted configuration holds `media.qbittorrent_password`; the WebUI username is `private-cloud`.
- The startup initializer applies the qBittorrent password before its WebUI starts.
- The installer maintains the `private-cloud` quality profile from the configured Sonarr and Radarr preferences.
- The profile accepts standard HDTV, WEB, and Blu-ray qualities from 720p through the selected resolution.
- The profile excludes remux, raw, disc, and low-quality theatrical sources.
- The profile stops automatic upgrades at Blu-ray in the selected resolution.
- Managed connections use names beginning with `private-cloud-`.

Indexers provide searchable release listings; quality profiles specify acceptable formats, resolutions, and upgrade cutoffs.

The integration uses the native [Prowlarr application settings](https://github.com/Prowlarr/Prowlarr/blob/develop/src/NzbDrone.Core/Applications/Sonarr/SonarrSettings.cs) and [Sonarr qBittorrent settings](https://github.com/Sonarr/Sonarr/blob/develop/src/NzbDrone.Core/Download/Clients/QBittorrent/QBittorrentSettings.cs).

## File logs

The pinned qBittorrent 5.1.2 application logger has no native stdout configuration, so qBittorrent alone receives a logging sidecar. Its [application source](https://github.com/qbittorrent/qBittorrent/blob/release-5.1.2/src/app/application.cpp) configures the file logger separately from startup console output.

- The `file-logs` sidecar forwards `/config/qBittorrent/logs/qbittorrent.log`.
- It emits JSON lines with `message`, `source_file`, and `collected_at` fields.
- The source log directory is mounted read-only.
- Read positions persist under `.log-forwarder` in the qBittorrent dataset.
- The native sidecar starts before application containers and stops after them.
- Recreate deployments prevent overlapping checkpoint writers.
- Sonarr, Radarr, Prowlarr, and qBittorrent use Recreate deployments so one database never has two writers.
- Pod annotations carry credential Secret revisions, never credential hashes.
- Sonarr, Radarr, and Prowlarr keep their native console logging.

The configuration is [file-logs.conf](files/file-logs.conf). It discovers new files every second, follows renamed files for 30 seconds, and resumes saved offsets after a restart. First collection reads the current file from the beginning. Rotated backups are excluded from discovery to prevent replay.

Forwarding is best effort across abrupt crashes or rotation during an outage. Lines larger than 1 MiB are skipped with a Fluent Bit warning. Original application timestamps remain inside `message`; `collected_at` records collection time.

The installer seeds qBittorrent defaults and the startup initializer reapplies logging, seeding limits, anonymous mode, and WebUI credentials on every pod start. File logging rotates at 10MiB and removes logs after seven days. An existing configuration must use the documented path; forwarding remains best effort during abrupt crashes, rotation, and collector outages.
