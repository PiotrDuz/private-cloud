# Immich service

The Immich service is managed by `ansible/roles/immich`.

- Configure `private_cloud.immich` in the public configuration.
- Store the database password in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/immich`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The PV stores the Immich media library.
- Immich uses a dedicated database on the shared VectorChord-enabled PostgreSQL service.
- The role enables and verifies `vector`, `vchord`, and `earthdistance` in the Immich database.
- Immich uses its disposable cluster-local Valkey service.
- Immich machine learning downloads face-detection and recognition models on demand.
- `machine_learning_accelerator: openvino` selects the Intel OpenVINO machine-learning image.
- OpenVINO requests one shared `gpu.intel.com/i915` resource.
- Fixed NodePort `30283` publishes the service over HTTP.
- Forward the Immich hostname to NodePort `30283` through the TLS proxy.
- Preserve WebSockets in the TLS proxy.
