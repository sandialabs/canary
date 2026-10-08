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
  -v .../.ci/assert_example_results.py:/root/assert_example_results.py \
  -e BRANCH_NAME=$BRANCH_NAME \
  -e ASSERT_EXAMPLES=/root/assert_example_results.py \
  ghcr.io/sandialabs/canary-slurm:latest \
  /bin/bash -c "./test.sh $BRANCH_NAME"
```

`test.sh` creates a venv, `pip install`s `canary-wm@git+...@$BRANCH_NAME`,
and runs the Slurm scheduler tests.

## Rebuilding and publishing the image

Build manually with:

```console
# Build only
./rebuild.sh

# Build and push
echo "$GHCR_TOKEN" | podman login ghcr.io -u <your-github-username> --password-stdin
PUSH=1 ./rebuild.sh
```

### Running the image locally

```console
podman run -it --rm \
  -v "$PWD/test.sh:/root/test.sh" \
  -v "$PWD/../assert_example_results.py:/root/assert_example_results.py" \
  -e BRANCH_NAME=main \
  -e ASSERT_EXAMPLES=/root/assert_example_results.py \
  ghcr.io/sandialabs/canary-slurm:latest \
  /bin/bash -c "./test.sh main"
```
