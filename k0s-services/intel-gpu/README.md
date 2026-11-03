# Intel GPU service

The Intel GPU device plugin is managed by `ansible/roles/intel_gpu`.

- The role installs Intel integrated graphics firmware and loads the `i915` driver.
- The plugin publishes three shared `gpu.intel.com/i915` allocations.
- Immich OpenVINO reserves one allocation for machine learning.
- Jellyfin reserves one allocation for transcoding when the stage is enabled.
- The Immich server reserves one allocation for video transcoding.
- The device plugin image is pinned to the Kubernetes 1.36-compatible release.
