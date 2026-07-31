#!/usr/bin/env bash
# Build the CoupFE-EDA container.
#
# The Dockerfile clones the public CoupFE repository from the documented branch, verifies that
# it contains the audited commit, and checks out that exact commit. No credentials or transient
# vendored source tree are used.
#
#   ./build.sh                            # build image with the pinned public core
#   COUPFE_REF=<sha> ./build.sh           # pin a specific CoupFE commit
#   TAG=myimg RUN_TOOLCHAIN_TESTS=1 ./build.sh
#
set -euo pipefail
EDA_ROOT="$(cd "$(dirname "$0")" && pwd)"
COUPFE_URL="${COUPFE_URL:-https://github.com/tengzhang48/CoupFE.git}"
COUPFE_BRANCH="${COUPFE_BRANCH:-main}"
COUPFE_REF="${COUPFE_REF:-933e497301ee3ddb23391b787726674f70b480c5}"
TAG="${TAG:-coupfe-eda}"
RUN_TOOLCHAIN_TESTS="${RUN_TOOLCHAIN_TESTS:-0}"

echo ">> checking public CoupFE branch: $COUPFE_URL ($COUPFE_BRANCH)"
git ls-remote --exit-code "$COUPFE_URL" "refs/heads/$COUPFE_BRANCH" >/dev/null

echo ">> docker build -t $TAG  (53-gate harness plus the full default pytest tier)"
EXTRA_ARGS=(
  --build-arg "COUPFE_URL=$COUPFE_URL"
  --build-arg "COUPFE_BRANCH=$COUPFE_BRANCH"
  --build-arg "COUPFE_REF=$COUPFE_REF"
  --build-arg "RUN_TOOLCHAIN_TESTS=$RUN_TOOLCHAIN_TESTS"
)
if [ -n "${OPENROAD_DEB_URL:-}" ] || [ -n "${OPENROAD_DEB_SHA256:-}" ]; then
  if [ -z "${OPENROAD_DEB_URL:-}" ] || [ -z "${OPENROAD_DEB_SHA256:-}" ]; then
    echo "ERROR: override OPENROAD_DEB_URL and OPENROAD_DEB_SHA256 together" >&2
    exit 2
  fi
  EXTRA_ARGS+=(
    --build-arg "OPENROAD_DEB_URL=$OPENROAD_DEB_URL"
    --build-arg "OPENROAD_DEB_SHA256=$OPENROAD_DEB_SHA256"
  )
fi
docker build -t "$TAG" \
  --label "coupfe.ref=$COUPFE_REF" \
  "${EXTRA_ARGS[@]}" \
  "$EDA_ROOT"
echo ">> done. image: $TAG (CoupFE @ $COUPFE_REF from $COUPFE_BRANCH)"
