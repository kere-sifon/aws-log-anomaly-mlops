#!/usr/bin/env bash
# Build terraform/files/bootstrap_model.tar.gz for the initial SageMaker model used by Terraform.
#
# Layout (SageMaker Scikit-learn container):
#   model.tar.gz
#   ├── model.joblib          # same bundle shape as training/train.py (dict: model, scaler, feature_columns, threshold)
#   └── code/
#         inference.py        # handlers (import name must match SAGEMAKER_PROGRAM in sagemaker.tf)
#         setup.py            # py_modules so "pip install ." exposes import inference
#
# Pin scikit-learn to a 1.2.x line compatible with the default inference image tag (e.g. 1.2-1-cpu-py3).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/terraform/files/bootstrap_model.tar.gz"
WORKDIR="$(mktemp -d)"
export WORKDIR
trap 'rm -rf "${WORKDIR}"' EXIT

mkdir -p "${WORKDIR}/code"
cp "${ROOT}/inference/inference.py" "${WORKDIR}/code/inference.py"
cp "${ROOT}/inference/setup.py" "${WORKDIR}/code/setup.py"

VENV="${WORKDIR}/venv"
python3 -m venv "${VENV}"
# shellcheck disable=SC1090
source "${VENV}/bin/activate"
python3 -m pip install -q -U pip setuptools wheel
# NumPy 2.x is ABI-incompatible with many sklearn 1.2 wheels → "numpy.dtype size changed".
python3 -m pip install -q "numpy>=1.24,<2" "scikit-learn==1.2.1,<1.3" "joblib>=1.3"

python3 <<'PY'
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import os

# Keep aligned with training/train.py FEATURE_COLUMNS so inference.py model_fn + predict dimensions match.
FEATURE_COLUMNS = [
    "message_length",
    "has_exception",
    "has_timeout",
    "has_connection_error",
    "level",
    "service_hash",
]

out_dir = os.environ["WORKDIR"]
path = os.path.join(out_dir, "model.joblib")
rng = np.random.default_rng(0)
X = rng.standard_normal((96, len(FEATURE_COLUMNS)))
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)
clf = IsolationForest(n_estimators=32, random_state=0, max_samples=96, contamination=0.05)
clf.fit(X_scaled)
scores = clf.score_samples(X_scaled)
payload = {
    "model": clf,
    "scaler": scaler,
    "feature_columns": FEATURE_COLUMNS,
    "threshold": float(np.quantile(scores, 0.05)),
}
joblib.dump(payload, path)
print("Wrote", path, flush=True)
PY

mkdir -p "$(dirname "${OUT}")"
tar -czf "${OUT}" -C "${WORKDIR}" model.joblib code
echo "Created ${OUT} ($(wc -c < "${OUT}") bytes)"
