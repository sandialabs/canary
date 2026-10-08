#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
IMAGE=${IMAGE:-ghcr.io/sandialabs/canary-pbs:latest}
BASE_IMAGE=${BASE_IMAGE:-pbspro/pbspro:latest}
BRANCH_NAME=${BRANCH_NAME:-main}
ASSERT_EXAMPLES=${ASSERT_EXAMPLES:-$SCRIPT_DIR/../assert_example_results.py}
PUSH=${PUSH:-0}

echo "Building $IMAGE from $BASE_IMAGE"
podman build --build-arg BASE_IMAGE="$BASE_IMAGE" --file "$SCRIPT_DIR/Dockerfile" --tag "$IMAGE" "$SCRIPT_DIR"

if [ "$PUSH" = "1" ]; then
  echo "Pushing $IMAGE"
  podman push "$IMAGE"
fi

podman run --rm --user root -h pbs \
  -v "$SCRIPT_DIR/test.sh:/tmp/testing/test.sh" \
  -v "$ASSERT_EXAMPLES:/tmp/testing/assert_example_results.py" \
  -e BRANCH_NAME="$BRANCH_NAME" \
  -e ASSERT_EXAMPLES=/tmp/testing/assert_example_results.py \
  -e PBS_START_MOM=1 \
  "$IMAGE" /tmp/testing/test.sh
