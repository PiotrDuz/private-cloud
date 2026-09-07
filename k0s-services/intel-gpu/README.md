# Intel GPU service

The Intel GPU device plugin is managed by `ansible/roles/intel_gpu`.

- The role installs Intel integrated graphics firmware and loads the `i915` driver.
- The plugin publishes two shared `gpu.intel.com/i915` allocations.
- Immich OpenVINO reserves one allocation for machine learning.
- A future media service can reserve the second allocation for transcoding.
- The device plugin image is pinned to the Kubernetes 1.36-compatible release.
