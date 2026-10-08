# CI Assets

This directory is intentionally small.

Keep only:
- scheduler test scripts used by GitHub/GitLab CI
- the shared example-results verifier
- rebuild/run helpers for containerized scheduler environments we need to recreate manually with `podman`

Current model:
- **Slurm** (`slurm/`): Canary-owned prebuilt image published to `ghcr.io/sandialabs/canary-slurm:latest`. CI pulls that image and installs the branch under test at runtime. The files under `slurm/` are the source of truth for rebuilding it with `podman`.
- **Flux** (`flux/`): CI uses the upstream `fluxrm/flux-sched:latest` image and mounts `flux/test.sh` plus the shared verifier into the container.
- **PBS** (`pbs/`): CI currently uses the upstream `pbspro/pbspro:latest` image and mounts `pbs/test.sh` plus the shared verifier into the container. The files under `pbs/` now also define a thin repo-owned image that can be rebuilt and pushed to `ghcr.io/sandialabs/canary-pbs:latest` with `podman` when we want to host our own copy.
