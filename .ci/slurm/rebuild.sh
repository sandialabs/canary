#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
IMAGE=${IMAGE:-ghcr.io/sandialabs/canary-slurm:latest}
PUSH=${PUSH:-0}

echo "Building $IMAGE from $SCRIPT_DIR"
podman build --file "$SCRIPT_DIR/Dockerfile" --tag "$IMAGE" "$SCRIPT_DIR"

if [ "$PUSH" = "1" ]; then
  echo "Pushing $IMAGE"
  podman push "$IMAGE"
fi
