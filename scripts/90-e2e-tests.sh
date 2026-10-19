#!/usr/bin/env bash
# Run the end-to-end test suite (pytest) against the live cluster.
source "$(dirname "$0")/lib.sh"
cd "$REPO_DIR"
python3 -m pytest tests/e2e -v -p no:cacheprovider "$@"
