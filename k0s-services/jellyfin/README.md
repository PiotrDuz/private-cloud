# Jellyfin service

The Jellyfin templates are managed by `ansible/roles/media` through the `media` installer stage.

- Configure the hostname and storage quota under `private_cloud.media`.
- Deploy Jellyfin in the `media` namespace.
- Store configuration in `tank/secure/backup/k0s/services/jellyfin`.
- Give the dataset a quota and a dedicated `10Ti` PV.
- Mount the shared `media-library-data` claim read-only at `/media`.
- Request one shared `gpu.intel.com/i915` allocation for transcoding.
- Publish the configured hostname through Traefik HTTPS.
- Accept TCP `8096` only from Traefik.
- Allow cluster DNS, Keycloak HTTPS, and Internet HTTPS egress.
- Keep online metadata and image downloads enabled.
- Disable subtitle fetchers, subtitle savers, unrelated plugins, and remote-media suggestions.

The [arr stack](../arr/README.md) provisions the shared library and downloads media independently of Jellyfin playback.

## Local library configuration

- A Python init container applies managed settings before the server starts.
- Initial libraries use `/media/movies` and `/media/tv` from the shared read-only mount.
- Existing library options retain their paths and keep metadata writes off the read-only mount.
- Automatic subtitle downloads and writes alongside media remain disabled.
- Only the pinned SSO-OIDC plugin is installed, and its manifest stays enabled with auto-update off.
- The server runs as UID 1000 with the host render-device group.
- Disable local metadata and artwork saving on newly added libraries because the mount is read-only.

Library settings follow Jellyfin's [LibraryOptions](https://github.com/jellyfin/jellyfin/blob/v10.11.4/MediaBrowser.Model/Configuration/LibraryOptions.cs) and [persisted library configuration](https://github.com/jellyfin/jellyfin/blob/v10.11.4/MediaBrowser.Controller/Entities/CollectionFolder.cs).

## SSO-OIDC login

- Jellyfin `10.11.4` runs the pinned plugin release `1.0.7.0`.
- The plugin `2.x` line requires Jellyfin 12, so keep both pins aligned.
- An `install-oidc-plugin` init container downloads `oidc-rbac.zip` from the `v1.0.7.0` release.
- The container verifies SHA-256 `84265ab9d374f9cfd53028fc78b6b27941f9f27e5c7fb61aeba9aa33016fe8bc` before extraction.
- The archive extracts to `/config/plugins/SSO-OIDC Authentication_1.0.7.0`.
- The plugin manifest stays `Active` with `autoUpdate` disabled.
- The `configure-local-library` init container renders `/config/plugins/configurations/Jellyfin.Plugin.OIDC.xml`.
- The provider id is `keycloak` and the authority is `https://<keycloak-hostname>/realms/private-cloud`.
- The client id is `jellyfin`.
- The client secret comes from the `jellyfin-credentials` Secret key `JELLYFIN_OIDC_CLIENT_SECRET`.
- Roles come from the `realm_access.roles` claim.
- The `jellyfin-admins` role maps to administrator with all libraries.
- The `jellyfin-users` role maps to the `Movies` and `TV` libraries.
- Login is denied when no role mapping matches.
- Quick Connect is enabled for native and mobile clients.
- Jellyfin's Login Disclaimer renders the Keycloak sign-in button.
- The init container preserves the Keycloak discovery pin fields.
- Private-network authority blocking stays off because Keycloak resolves to the LAN address.
- Edit role mappings in `media/jellyfin_helpers.py`, not in the plugin admin UI.

### Keycloak operator steps

- Create the confidential client `jellyfin` in realm `private-cloud`.
- Allow the redirect URI `https://<jellyfin-hostname>/sso/OIDC/Callback/keycloak`.
- Assign the `roles` client scope so realm roles reach the `realm_access.roles` claim.
- Create and assign the realm roles `jellyfin-admins` and `jellyfin-users`.
- Run **Test Connection** in the plugin admin page to verify and pin the Keycloak discovery endpoints.
- Keep one local password administrator as a break-glass account.
- Open `https://<jellyfin-hostname>/sso/OIDC/QuickConnect/keycloak` to authorize a native app.

## Logging

Jellyfin supports native console logging and receives no logging sidecar. The pinned image enables the Console sink in its [default logging configuration](https://github.com/jellyfin/jellyfin/blob/v10.11.4/Jellyfin.Server/Resources/Configuration/logging.json).

Server logs are available from the main container. Separate FFmpeg diagnostic logs remain under `/config/log` on the Jellyfin dataset and are not forwarded to stdout. A host timer prunes closed FFmpeg `.log` and `.txt` files after seven days or when their combined size exceeds 1GiB; active files remain untouched.

```bash
sudo k0s kubectl logs -n media deployment/jellyfin -c jellyfin --follow
```
