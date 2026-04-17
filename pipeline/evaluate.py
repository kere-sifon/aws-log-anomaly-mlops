#!/usr/bin/env python3
"""
SageMaker Processing job: score holdout with trained Isolation Forest and emit ``evaluation.json`` (F1).
"""
from __future__ import annotations

import json
import logging
import sys
import tarfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _load_model(model_dir: Path):
    """Load ``model.joblib`` from extracted training artifact tarball or flat dir."""
    tarballs = list(model_dir.glob("*.tar.gz")) + list(model_dir.glob("model.tar.gz"))
    if tarballs:
        extract_root = model_dir / "extracted"
        extract_root.mkdir(exist_ok=True)
        with tarfile.open(tarballs[0], "r:gz") as tar:
            tar.extractall(path=extract_root)
        candidates = list(extract_root.rglob("model.joblib"))
        if not candidates:
            raise FileNotFoundError("model.joblib not found in model artifact archive.")
        payload = joblib.load(candidates[0])
    else:
        direct = model_dir / "model.joblib"
        if not direct.exists():
            raise FileNotFoundError("Expected model tarball or model.joblib under model channel.")
        payload = joblib.load(direct)
    bundle = payload if isinstance(payload, dict) else {"model": payload}
    return bundle["model"]


def main() -> None:
    model_dir = Path("/opt/ml/processing/model")
    holdout_path = Path("/opt/ml/processing/holdout/eval.csv")
    eval_out_dir = Path("/opt/ml/processing/evaluation")
    eval_out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading holdout from %s", holdout_path)
    df = pd.read_csv(holdout_path)
    if "label" not in df.columns:
        raise ValueError("Holdout requires a 'label' column (1=anomaly, 0=normal).")
    labels = df["label"].astype(int).values
    feature_cols = [c for c in df.columns if c != "label"]
    x = df[feature_cols].to_numpy(dtype=np.float32, copy=False)

    model = _load_model(model_dir)
    logger.info("Scoring holdout rows=%s", x.shape[0])

    raw_pred = model.predict(x)
    pred_anomaly = (raw_pred == -1).astype(int)
    f1 = float(f1_score(labels, pred_anomaly, average="binary", zero_division=0))

    report = {
        "f1_score": f1,
        "classification_metrics": {
            "f1_binary": f1,
            "holdout_rows": int(x.shape[0]),
        },
    }
    out_file = eval_out_dir / "evaluation.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Wrote metrics f1_score=%.4f to %s", f1, out_file)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Evaluation failed")
        sys.exit(1)
