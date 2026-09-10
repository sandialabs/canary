# Slurm Container

This directory defines a **pre-built** Slurm container used for automated
pull-request testing. Building Slurm from source is too expensive to do on
every CI run, so the image is built once and published to the GitHub
Container Registry (GHCR). CI then *pulls* the image and installs the
canary branch under test at runtime.

## What the image contains

- A fully built and configured Slurm `23.02.7` (see `install_slurm.sh`).
- MariaDB (Slurm accounting), munge, MPICH, and Python 3.12.
- It does **not** contain canary. Canary is installed at runtime by
  `test.sh` from the branch/PR being tested, so the same image is reusable
  by every CI run.

## How CI uses it

The `slurm` job in `.github/workflows/workflow.yml` does:

```yaml
docker pull ghcr.io/sandialabs/canary-slurm:latest
docker run --rm \
  -v .../.ci/slurm/test.sh:/root/test.sh \
  -e BRANCH_NAME=$BRANCH_NAME \
  ghcr.io/sandialabs/canary-slurm:latest \
  /bin/bash -c "./test.sh $BRANCH_NAME"
```

`test.sh` creates a venv, `pip install`s `canary-wm@git+...@$BRANCH_NAME`,
and runs the Slurm scheduler tests.

## Rebuilding and publishing the image

The image is rebuilt automatically by the
`.github/workflows/build-slurm-container.yml` workflow whenever anything in
`.ci/slurm/**` changes on `main`, or on demand via **Run workflow**. That
workflow pushes to `ghcr.io/sandialabs/canary-slurm:latest`.

### Building and pushing manually (from outside CI)

If you need to build and push the image by hand (for example, the first
time, before the workflow exists in `main`):

```console
# 1. Build the base image
docker build --file Dockerfile --tag ghcr.io/sandialabs/canary-slurm:latest .

# 2. Log in to GHCR with a personal access token that has `write:packages`
echo "$GHCR_TOKEN" | docker login ghcr.io -u <your-github-username> --password-stdin

# 3. Push
docker push ghcr.io/sandialabs/canary-slurm:latest
```

### Running the image locally

```console
docker run -it --rm \
  -v "$PWD/test.sh:/root/test.sh" \
  -e BRANCH_NAME=main \
  ghcr.io/sandialabs/canary-slurm:latest \
  /bin/bash -c "./test.sh main"
```
