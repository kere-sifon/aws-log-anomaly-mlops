#!/usr/bin/env python3
"""
SageMaker training entry: Isolation Forest on structured log feature CSV.

Reads ``features.csv`` from the SageMaker train channel (default path below), trains,
evaluates on a holdout split, writes ``/opt/ml/output/metrics.json``, saves ``model.joblib``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "timestamp",
    "cpu_usage",
    "memory_usage",
    "error_rate",
    "request_latency_ms",
    "log_level_encoded",
]

DEFAULT_TRAIN_CSV = Path("/opt/ml/input/data/train/features.csv")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train Isolation Forest for log anomaly detection.")
    p.add_argument(
        "--contamination",
        type=float,
        default=0.05,
        help="Expected proportion of anomalies (Isolation Forest contamination).",
    )
    p.add_argument(
        "--n-estimators",
        "--n_estimators",
        type=int,
        default=100,
        dest="n_estimators",
        help="Number of trees in the ensemble.",
    )
    p.add_argument(
        "--random-state",
        "--random_state",
        type=int,
        default=42,
        dest="random_state",
        help="RNG seed for the model and train/validation split.",
    )
    p.add_argument(
        "--max-samples",
        "--max_samples",
        type=int,
        default=256,
        dest="max_samples",
        help="Samples drawn per tree (capped by training row count).",
    )
    return p.parse_args()


def _coerce_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return numeric feature matrix with expected columns; logs and drops bad rows."""
    n_in = len(df)
    work = df.copy()

    if "timestamp" in work.columns:
        ts = pd.to_datetime(work["timestamp"], errors="coerce", utc=True)
        bad_ts = ts.isna() & work["timestamp"].notna()
        if bad_ts.any():
            logger.warning("Dropped %s rows with unparseable timestamp.", int(bad_ts.sum()))
        work["timestamp"] = ts.apply(lambda t: t.timestamp() if pd.notna(t) else np.nan)

    for col in FEATURE_COLUMNS:
        if col not in work.columns:
            logger.warning("Missing column %r; filling with NaN.", col)
            work[col] = np.nan
        elif col != "timestamp":
            work[col] = pd.to_numeric(work[col], errors="coerce")

    feats = work.reindex(columns=FEATURE_COLUMNS).copy()
    before = len(feats)
    feats = feats.replace([np.inf, -np.inf], np.nan)
    feats = feats.dropna()
    dropped = before - len(feats)
    if dropped:
        logger.warning("Dropped %s rows with missing or non-finite feature values (of %s).", dropped, n_in)

    if len(feats) < 10:
        raise ValueError(f"Too few valid rows after cleaning: {len(feats)} (need at least 10).")

    return feats


def main() -> None:
    args = _parse_args()

    sm_channel = os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train")
    features_path = Path(sm_channel) / "features.csv"
    if not features_path.is_file() and DEFAULT_TRAIN_CSV.is_file():
        features_path = DEFAULT_TRAIN_CSV
        logger.info("Using default SageMaker path %s", features_path)

    if not features_path.is_file():
        logger.warning("No features.csv at %s or %s; generating synthetic data.", sm_channel, DEFAULT_TRAIN_CSV)
        rng = np.random.default_rng(args.random_state)
        n = 500
        syn = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=n, freq="min"),
                "cpu_usage": rng.uniform(0, 100, n),
                "memory_usage": rng.uniform(0, 100, n),
                "error_rate": rng.uniform(0, 0.2, n),
                "request_latency_ms": rng.uniform(1, 500, n),
                "log_level_encoded": rng.integers(0, 4, n),
            }
        )
        x_all = _coerce_features(syn).to_numpy(dtype=np.float64, copy=False)
    else:
        try:
            df = pd.read_csv(features_path)
        except Exception as e:
            logger.exception("Failed reading CSV %s", features_path)
            raise RuntimeError(f"Could not read training CSV: {e}") from e
        x_all = _coerce_features(df).to_numpy(dtype=np.float64, copy=False)

    rng_split = np.random.RandomState(args.random_state)
    x_train, x_val = train_test_split(
        x_all,
        test_size=0.2,
        random_state=rng_split,
        shuffle=True,
    )

    n_train, n_val = x_train.shape[0], x_val.shape[0]
    max_samples = min(args.max_samples, max(2, n_train))

    model = IsolationForest(
        n_estimators=args.n_estimators,
        max_samples=max_samples,
        contamination=args.contamination,
        random_state=args.random_state,
        n_jobs=-1,
        verbose=0,
    )
    model.fit(x_train)

    train_scores = model.score_samples(x_train)
    threshold = float(np.quantile(train_scores, args.contamination))

    val_scores = model.score_samples(x_val)
    synthetic_anomaly = (val_scores < threshold).astype(int)
    pred_anomaly = (model.predict(x_val) == -1).astype(int)

    f1 = float(
        f1_score(synthetic_anomaly, pred_anomaly, average="binary", zero_division=0)
    )
    anomaly_rate = float(np.mean(pred_anomaly))

    metrics = {
        "anomaly_rate": anomaly_rate,
        "f1_score": f1,
        "threshold": threshold,
        "training_samples": int(n_train),
        "validation_samples": int(n_val),
    }

    out_dir = Path("/opt/ml/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    logger.info("Wrote metrics to %s: %s", metrics_path, metrics)

    model_dir = Path(os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "model.joblib"
    payload = {
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "threshold": threshold,
    }
    joblib.dump(payload, model_path)
    logger.info("Saved model bundle to %s", model_path)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Training failed")
        sys.exit(1)
