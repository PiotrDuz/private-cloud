# Jellyfin service

The Jellyfin templates are managed by `ansible/roles/media` through the `media` installer stage.

- Configure the hostname and storage quota under `private_cloud.media`.
- Deploy Jellyfin in the `media` namespace.
- Store configuration in `tank/secure/backup/k0s/services/jellyfin`.
- Give the dataset a quota and a dedicated `10Ti` PV.
- Mount the shared `media-library-data` claim read-only at `/media`.
- Request one shared `gpu.intel.com/i915` allocation for transcoding.
- Publish the configured hostname through Traefik HTTPS.
- Accept TCP `8096` only from Traefik and deny initiated network traffic.
- Keep online metadata, subtitle, plugin, and remote-media integrations disabled.

The [arr stack](../arr/README.md) provisions the shared library and downloads media independently of Jellyfin playback.

## Logging

Jellyfin supports native console logging and receives no logging sidecar. The pinned image enables the Console sink in its [default logging configuration](https://github.com/jellyfin/jellyfin/blob/v10.11.4/Jellyfin.Server/Resources/Configuration/logging.json).

Server logs are available from the main container. Separate FFmpeg diagnostic logs remain under `/config/log` on the Jellyfin dataset and are not forwarded to stdout by this configuration.

```bash
sudo k0s kubectl logs -n media deployment/jellyfin -c jellyfin --follow
```
