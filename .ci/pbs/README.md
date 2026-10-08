# PBS Container

PBS CI currently uses the upstream `pbspro/pbspro:latest` image. This
directory also defines a thin repo-owned wrapper image so we can publish a
known PBS base to GitHub Container Registry when needed.

Build locally with:

```console
./rebuild.sh
```

Build and push to GitHub Container Registry with:

```console
echo "$GHCR_TOKEN" | podman login ghcr.io -u <your-github-username> --password-stdin
PUSH=1 ./rebuild.sh
```

Override the upstream base image, published tag, or branch under test if needed:

```console
BASE_IMAGE=pbspro/pbspro:latest IMAGE=ghcr.io/sandialabs/canary-pbs:latest BRANCH_NAME=my-branch ./rebuild.sh
```

The rebuild helper then runs the PBS test script locally with `podman run` so
the built image is validated immediately.
