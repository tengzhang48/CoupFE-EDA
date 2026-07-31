#!/usr/bin/env bash
# Set up CoupFE-EDA: clone the CoupFE core and install it + this project (editable).
#
# CoupFE stays a PINNED dependency, never edited here — this keeps the core lean and
# lets CoupFE-EDA grow independently. Run after creating/activating the env
# (see environment.yml), from the repo root.
#
#   ./setup.sh
#
# Env vars:
#   COUPFE_URL     - public clone URL
#   COUPFE_BRANCH  - public branch that must contain the audited commit
#   COUPFE_DIR     - dedicated dependency checkout (default: .deps/CoupFE)
#   COUPFE_REF     - exact audited commit
set -euo pipefail

EDA_ROOT="$(cd "$(dirname "$0")" && pwd)"
COUPFE_URL="${COUPFE_URL:-https://github.com/tengzhang48/CoupFE.git}"
COUPFE_BRANCH="${COUPFE_BRANCH:-main}"
COUPFE_DIR="${COUPFE_DIR:-$EDA_ROOT/.deps/CoupFE}"
COUPFE_REF="${COUPFE_REF:-454f73ce2de284262b214a2b37bd676c6aca3c0a}"

if [ ! -d "$COUPFE_DIR/.git" ]; then
  if [ -e "$COUPFE_DIR" ]; then
    echo "ERROR: COUPFE_DIR exists but is not a Git checkout: $COUPFE_DIR" >&2
    exit 2
  fi
  echo ">> cloning CoupFE core -> $COUPFE_DIR"
  mkdir -p "$(dirname "$COUPFE_DIR")"
  git clone --branch "$COUPFE_BRANCH" --single-branch "$COUPFE_URL" "$COUPFE_DIR"
else
  ACTUAL_URL="$(git -C "$COUPFE_DIR" remote get-url origin)"
  if [ "$ACTUAL_URL" != "$COUPFE_URL" ]; then
    echo "ERROR: $COUPFE_DIR origin is '$ACTUAL_URL', expected '$COUPFE_URL'." >&2
    echo "Use a fresh COUPFE_DIR or set COUPFE_URL explicitly; no checkout was changed." >&2
    exit 2
  fi
fi

echo ">> verifying public branch $COUPFE_BRANCH contains $COUPFE_REF"
git -C "$COUPFE_DIR" fetch --force origin \
  "refs/heads/$COUPFE_BRANCH:refs/remotes/origin/$COUPFE_BRANCH"
git -C "$COUPFE_DIR" cat-file -e "$COUPFE_REF^{commit}"
if ! git -C "$COUPFE_DIR" merge-base --is-ancestor \
  "$COUPFE_REF" "refs/remotes/origin/$COUPFE_BRANCH"; then
  echo "ERROR: audited commit is not reachable from origin/$COUPFE_BRANCH" >&2
  exit 2
fi

echo ">> pinning dedicated CoupFE checkout @ $COUPFE_REF"
git -C "$COUPFE_DIR" checkout --detach "$COUPFE_REF"
RESOLVED_REF="$(git -C "$COUPFE_DIR" rev-parse HEAD)"
if [ "$RESOLVED_REF" != "$COUPFE_REF" ]; then
  echo "ERROR: resolved CoupFE commit '$RESOLVED_REF' != '$COUPFE_REF'" >&2
  exit 2
fi
if [ -n "$(git -C "$COUPFE_DIR" status --porcelain=v1 --untracked-files=all)" ]; then
  echo "ERROR: pinned CoupFE checkout is not clean: $COUPFE_DIR" >&2
  exit 2
fi

echo ">> installing CoupFE core (editable)"
python -m pip install -e "$COUPFE_DIR"
echo ">> installing CoupFE-EDA with development/release tools (editable)"
python -m pip install -e "${EDA_ROOT}[dev]"

echo ">> verifying the imported clean public CoupFE checkout"
PYTHONDONTWRITEBYTECODE=1 python "$EDA_ROOT/.github/scripts/check_runtime_core.py" \
  --expected-url "$COUPFE_URL" \
  --expected-branch "$COUPFE_BRANCH" \
  --expected-ref "$COUPFE_REF" \
  --expected-root "$COUPFE_DIR"

echo
echo "Done. Verify the trust suite:"
echo "    python -m eda_multiphysics.run        # component/reference harness"
echo "    python -m pytest -q                   # default tier, including harness wrappers"
echo
echo "Distributed PDN (optional; included by environment.yml):"
echo "    mpirun -n 4 python -m eda_multiphysics.pdn_distributed 400 [--direct]"
