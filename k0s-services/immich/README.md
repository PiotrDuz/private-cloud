# Immich service

The Immich service is managed by `ansible/roles/immich`.

- The installer reads `private_cloud.immich` from the public configuration.
- The encrypted configuration holds the database password and the OIDC client secret.
- The service dataset is `tank/secure/backup/k0s/services/immich`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The PV stores the Immich media library.
- The dataset is mounted at `/data` and the media location is `/data/library`.
- The library directory stays private as `0750` owned by `root:root`.
- An init container normalizes the library ownership inside the pod user namespace.
- Immich uses a dedicated database on the shared VectorChord-enabled PostgreSQL service.
- The role enables and verifies `vector`, `vchord`, and `earthdistance` in the Immich database.
- Immich uses its disposable cluster-local `valkey-immich` service.
- Immich machine learning downloads face-detection and recognition models on demand.
- `machine_learning_accelerator: openvino` selects the Intel OpenVINO machine-learning image.
- OpenVINO requests one shared `gpu.intel.com/i915` resource.
- GPU buffers count against the container memory, so OpenVINO needs `machine_learning_max_ram` of at least `4Gi`.
- A ClusterIP service exposes TCP `2283` only inside the cluster.
- Traefik publishes the configured hostname through HTTPS.
- The installer creates the first administrator as the managed Stalwart mailbox account before applying the route ConfigMap.
- The installer skips the claim when Immich reports `isInitialized`.
- The pod annotation carries the credentials Secret revision to restart the pod on rotation.
- The route ConfigMap preserves WebSocket connections.

## Stalwart OIDC

- Immich uses native OIDC with the Stalwart issuer `https://<stalwart hostname>`.
- The confidential `immich` client allows the `https://<immich hostname>/auth/login` and `https://<immich hostname>/user-settings` redirects.
- The client also allows the `https://<immich hostname>/api/oauth/mobile-redirect` mobile redirect.
- Immich enables the mobile redirect override, so mobile sign-in returns through the HTTPS redirect.
- ID token validation uses `ES256` to match the Stalwart signing key.
- The encrypted configuration holds the client secret as `immich.oidc_client_secret`.
- An init container renders the client secret into `/config/immich-config.json` from the `IMMICH_OAUTH_*` environment.
- The server reads the rendered configuration through `IMMICH_CONFIG_FILE`.
- System settings are managed through the configuration file.
- The web UI configuration editor is disabled while the configuration file is mounted.
- Automatic OAuth registration creates accounts for Stalwart users on first sign-in.
- The first administrator is the managed Stalwart mailbox account, so its sign-in links to the claimed account.
- Administrator rights for other users are granted inside Immich.
- Auto-launch sends users to Stalwart; `/auth/login?autoLaunch=0` shows the local form.
