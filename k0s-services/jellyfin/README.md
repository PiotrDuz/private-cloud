# Jellyfin service

The Jellyfin templates are managed by `ansible/roles/media` through the `media` installer stage.

- Configure the hostname and storage quota under `private_cloud.media`.
- Deploy Jellyfin in the `media` namespace.
- Store configuration in `tank/secure/backup/k0s/services/jellyfin`.
- Give the dataset a quota and a dedicated `10Ti` PV.
- Mount the shared `media-library-data` claim read-only at `/media`.
- Request one shared `gpu.intel.com/i915` allocation for transcoding.
- Publish the configured hostname through Traefik HTTPS.
- Accept TCP `8096` only from Traefik and allow cluster DNS plus Internet HTTPS for metadata.
- Keep metadata and artwork download enabled while disabling subtitle, plugin, and remote-media integrations.

The [arr stack](../arr/README.md) provisions the shared library and downloads media independently of Jellyfin playback.

## Local library configuration

- A Python init container applies managed settings before the server starts.
- Initial libraries use `/media/movies` and `/media/tv` from the shared read-only mount.
- Existing library options retain their paths and keep metadata writes off the read-only mount.
- Automatic subtitle downloads and writes alongside media remain disabled.
- Plugin repositories and installed plugin manifests are disabled at startup.
- The server runs as UID 1000 with the host render-device group.
- NetworkPolicy permits cluster DNS and Internet TCP `443` only.
- Disable local metadata and artwork saving on newly added libraries because the mount is read-only.

Library settings follow Jellyfin's [LibraryOptions](https://github.com/jellyfin/jellyfin/blob/v10.11.4/MediaBrowser.Model/Configuration/LibraryOptions.cs) and [persisted library configuration](https://github.com/jellyfin/jellyfin/blob/v10.11.4/MediaBrowser.Controller/Entities/CollectionFolder.cs).

## Logging

Jellyfin supports native console logging and receives no logging sidecar. The pinned image enables the Console sink in its [default logging configuration](https://github.com/jellyfin/jellyfin/blob/v10.11.4/Jellyfin.Server/Resources/Configuration/logging.json).

Server logs are available from the main container. Separate FFmpeg diagnostic logs remain under `/config/log` on the Jellyfin dataset and are not forwarded to stdout. A host timer prunes closed FFmpeg `.log` and `.txt` files after seven days or when their combined size exceeds 1GiB; active files remain untouched.

```bash
sudo k0s kubectl logs -n media deployment/jellyfin -c jellyfin --follow
```
