# Docker Containers

This directory contains Docker containers that can be used for automated pull request testing. There are subdirectories for each scheduler type (i.e. slurm/). Additionally, the standalone directory contains just a Dockerfile for a canary container.

## Pre-built vs. build-at-CI images

- **Slurm** (`slurm/`): the image is **pre-built** and published to the
  GitHub Container Registry (`ghcr.io/sandialabs/canary-slurm`). Building
  Slurm from source on every CI run is too slow, so the `slurm` CI job pulls
  the pre-built image and installs the canary branch under test at runtime.
  See `slurm/README.md` and `.github/workflows/build-slurm-container.yml`.
- **Flux** / **PBS**: pulled directly from upstream registries
  (`fluxrm/flux-sched`, `pbspro/pbspro`) with canary installed at runtime.

## Python Versions

As of July 3rd, 2025, flux is running python 3.10 and the slurm container is running python 3.12. Upgrading python inside the flux container (for the CI pipeline) is not possible because it is pulled from flux's docker registry. However, with the `Dockerfile`, the slurm and flux (for container testing) python versions can be upgraded at any time.  
