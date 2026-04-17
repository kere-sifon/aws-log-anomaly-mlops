#!/usr/bin/env bash
# Build terraform/files/bootstrap_model.tar.gz for the initial SageMaker model used by Terraform.
# The tarball must contain model.joblib at the root (SageMaker Scikit-learn container layout).
# Pin scikit-learn to a 1.2.x line compatible with the default inference image tag (e.g. 1.2-1-cpu-py3).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/terraform/files/bootstrap_model.tar.gz"
WORKDIR="$(mktemp -d)"
export WORKDIR
trap 'rm -rf "${WORKDIR}"' EXIT

VENV="${WORKDIR}/venv"
python3 -m venv "${VENV}"
# shellcheck disable=SC1090
source "${VENV}/bin/activate"
python3 -m pip install -q "numpy>=1.24,<3" "scikit-learn>=1.2,<1.3" "joblib>=1.3"

python3 <<'PY'
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
import os

out_dir = os.environ["WORKDIR"]
path = os.path.join(out_dir, "model.joblib")
# Minimal fitted model so the prebuilt sklearn container can load it and pass /ping.
rng = np.random.default_rng(0)
X = rng.standard_normal((64, 5))
clf = IsolationForest(n_estimators=32, random_state=0, max_samples=64, contamination=0.05)
clf.fit(X)
joblib.dump(clf, path)
print("Wrote", path, flush=True)
PY

mkdir -p "$(dirname "${OUT}")"
tar -czf "${OUT}" -C "${WORKDIR}" model.joblib
echo "Created ${OUT} ($(wc -c < "${OUT}") bytes)"
