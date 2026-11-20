#!/usr/bin/env bash
# From a release checkout. SSH policy and Metal access belong to the existing macOS login.
set -euo pipefail
ref=${1:?usage: deploy.sh GIT_REF ENGINE_VERSION}
version=${2:?missing engine version}
[[ $version =~ ^[a-zA-Z0-9._-]{1,64}$ ]]
remote=${VIBECHECKER_M6_HOST:-youwenshao@mac-mini-m6.tail1e0617.ts.net}
revision=$(git rev-parse --verify --end-of-options "$ref^{commit}")
dest="vibechecker/releases/$revision"
ssh -o BatchMode=yes "$remote" "umask 077 && mkdir -p '$dest'"
git archive "$revision" engine services/inference ops/m6 pyproject.toml uv.lock modal/pyproject.toml eval |
  ssh -o BatchMode=yes "$remote" "tar -x -C '$dest'"
ssh -o BatchMode=yes "$remote" "cd '$dest' && UV_PROJECT_ENVIRONMENT=\$HOME/vibechecker/venv /opt/homebrew/bin/uv sync --locked --all-packages --extra metal --no-dev && \$HOME/vibechecker/venv/bin/python ops/m6/install.py --version '$version'"
