# Immich service

The Immich service is managed by `ansible/roles/immich`.

- Configure `private_cloud.immich` in the public configuration.
- Store the database password and the OIDC client secret in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
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
- A ClusterIP service exposes TCP `2283` only inside the cluster.
- Traefik publishes the configured hostname through HTTPS.
- The Ingress preserves WebSocket connections.

## Keycloak OIDC

- Immich uses native OIDC with the Keycloak issuer `https://<keycloak hostname>/realms/private-cloud`.
- The confidential `immich` client allows the `https://<immich hostname>/auth/login` and `https://<immich hostname>/user-settings` redirects.
- The client also allows the `app.immich:///oauth-callback` mobile redirect.
- The client Backchannel logout URL is `https://<immich hostname>/api/oauth/backchannel-logout`.
- Store the client secret as `immich.oidc_client_secret` in the encrypted configuration.
- An init container renders the client secret into `/config/immich-config.json` from the `IMMICH_OAUTH_*` environment.
- The server reads the rendered configuration through `IMMICH_CONFIG_FILE`.
- System settings are managed through the configuration file.
- The web UI configuration editor is disabled while the configuration file is mounted.
- Automatic OAuth registration is disabled so only approved users receive accounts.
- Create the Immich user with the Keycloak email before the first login.
- Grant administrator rights explicitly in Immich.
- Do not add an `immich_role` claim to the Keycloak client.
- Auto-launch sends users to Keycloak; use `/auth/login?autoLaunch=0` for the local form.
