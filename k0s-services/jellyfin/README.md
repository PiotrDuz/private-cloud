# Jellyfin service

The Jellyfin templates are managed by `ansible/roles/media` through the `media` installer stage.

- `private_cloud.media` sets the hostname and storage quota.
- Jellyfin runs in the `media` namespace.
- Configuration lives in `tank/secure/backup/k0s/services/jellyfin`.
- The dataset has a quota and a dedicated `10Ti` PV.
- The shared `media-library-data` claim is mounted read-only at `/media`.
- The pod requests one shared `gpu.intel.com/i915` allocation for transcoding.
- Intel Quick Sync transcoding is enabled when the `intel_gpu` stage is enabled.
- Traefik publishes the configured hostname through HTTPS.
- The installer applies the route ConfigMap only after it completes the startup wizard.
- The installer creates the administrator named by `private_cloud.media.jellyfin_admin_username` with `private_cloud_secrets.media.jellyfin_admin_password`.
- The startup wizard is skipped when Jellyfin already reports it completed.
- The installer skips the wizard's configuration step so the managed settings stay unchanged.
- `fsGroupChangePolicy: OnRootMismatch` keeps starts from re-owning volumes.
- The shared library claim is read-only at both the volume and the mount.
- `KnownProxies` trusts forwarded headers only from the cluster pod network.
- TCP `8096` accepts traffic only from Traefik.
- Egress allows cluster DNS and Internet HTTPS.
- Online metadata and image downloads stay enabled.
- Subtitle fetchers, subtitle savers, unrelated plugins, and remote-media suggestions are disabled.

The [arr stack](../arr/README.md) provisions the shared library and downloads media independently of Jellyfin playback.

## Local library configuration

- A Python init container applies managed settings before the server starts.
- Initial libraries use `/media/movies` and `/media/tv` from the shared read-only mount.
- Existing library options retain their paths and keep metadata writes off the read-only mount.
- The init container writes `KnownProxies` in `network.xml` from `private_cloud.networking.pod_cidr`.
- The Jellyfin NetworkPolicy admits only Traefik, so the pod network can only be Traefik.
- Automatic subtitle downloads and writes alongside media remain disabled.
- The server runs as the dedicated media UID 2000 with the host render-device group.
- Newly added libraries need local metadata and artwork saving off because the mount is read-only.

Library settings follow Jellyfin's [LibraryOptions](https://github.com/jellyfin/jellyfin/blob/v10.11.4/MediaBrowser.Model/Configuration/LibraryOptions.cs) and [persisted library configuration](https://github.com/jellyfin/jellyfin/blob/v10.11.4/MediaBrowser.Controller/Entities/CollectionFolder.cs).

## Authentication

- Jellyfin uses native usernames and passwords, not Stalwart sign-in.
- Users, administrator grants, and library access live in Jellyfin.
- Native Quick Connect remains enabled for supported clients.
- The shared media library remains owned independently of Jellyfin accounts.

## Logging

Jellyfin supports native console logging and receives no logging sidecar. The pinned image enables the Console sink in its [default logging configuration](https://github.com/jellyfin/jellyfin/blob/v10.11.4/Jellyfin.Server/Resources/Configuration/logging.json).

Server logs come from the main container. Separate FFmpeg diagnostic logs remain under `/config/log` on the Jellyfin dataset and are not forwarded to stdout. Jellyfin's daily Clean Log Directory task deletes FFmpeg logs older than the configured three-day `LogFileRetentionDays`.
