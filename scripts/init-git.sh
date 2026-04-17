#!/usr/bin/env bash
# Initialize this repo with branch "develop" and an initial commit, then print next steps for GitHub/GitLab.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Git is already initialized (current branch: $(git branch --show-current))."
  exit 0
fi

git init -b develop
git add -A
git -c user.name="${GIT_AUTHOR_NAME:-aws-log-anomaly-mlops}" \
  -c user.email="${GIT_AUTHOR_EMAIL:-you@example.com}" \
  commit -m "Initial commit: Terraform, SageMaker pipeline, GitHub Actions"

git config init.defaultBranch develop

echo ""
echo "Done. Default branch: develop"
echo "Create an empty repository on your host, then:"
echo "  git remote add origin <HTTPS-or-SSH-URL>"
echo "  git push -u origin develop"
