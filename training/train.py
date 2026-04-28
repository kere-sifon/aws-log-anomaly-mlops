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
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "message_length",
    "has_exception",
    "has_timeout",
    "has_connection_error",
    "level",
    "service_hash",
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


def _legacy_schema_ready(work: pd.DataFrame) -> bool:
    """True when CSV looks like the canonical log-monitoring feature table."""
    needed = sum(1 for c in FEATURE_COLUMNS if c in work.columns)
    # Require every named column — older synthetic / integration tests use exactly this schema.
    return needed == len(FEATURE_COLUMNS)


def _coerce_features_legacy(work: pd.DataFrame) -> pd.DataFrame:
    """Coerce the canonical log-content feature columns to numeric."""
    n_in = len(work)
    for col in FEATURE_COLUMNS:
        if col not in work.columns:
            logger.warning("Missing column %r; filling with NaN.", col)
            work[col] = np.nan
        else:
            work[col] = pd.to_numeric(work[col], errors="coerce")

    feats = work.reindex(columns=FEATURE_COLUMNS).copy()
    before = len(feats)
    feats = feats.replace([np.inf, -np.inf], np.nan)
    feats = feats.dropna()
    dropped = before - len(feats)
    if dropped:
        logger.warning("Dropped %s rows with missing or non-finite feature values (of %s).", dropped, n_in)
    return feats


def _coerce_features_dynamic(work: pd.DataFrame) -> pd.DataFrame:
    """Use all preprocess/engineered numeric columns (Pipeline + arbitrary log CSV/JONL-derived names)."""
    n_in = len(work)
    frame = pd.DataFrame(index=work.index)
    for col in work.columns:
        if col == "timestamp":
            ts = pd.to_datetime(work[col], errors="coerce", utc=True)
            bad_ts = ts.isna() & work[col].notna()
            if bad_ts.any():
                logger.warning("Dropped %s rows with unparseable timestamp.", int(bad_ts.sum()))
            frame[col] = ts.map(lambda t: t.timestamp() if pd.notna(t) else np.nan)
        else:
            frame[col] = pd.to_numeric(work[col], errors="coerce")
    before = len(frame)
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    dropped = before - len(frame)
    if dropped:
        logger.warning(
            "Dropped %s rows with missing or non-finite feature values (of %s).",
            dropped,
            n_in,
        )
    return frame


def _coerce_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Return numeric feature matrix and column order for serialization / inference."""
    work = df.copy()
    if "label" in work.columns:
        work = work.drop(columns=["label"])

    if _legacy_schema_ready(work):
        logger.info("Using legacy FEATURE_COLUMNS schema (%s).", FEATURE_COLUMNS)
        feats = _coerce_features_legacy(work)
        cols = list(FEATURE_COLUMNS)
    else:
        logger.info(
            "Using dynamic feature columns from CSV (%s); pipeline preprocess output aligns with this path.",
            list(work.columns),
        )
        feats = _coerce_features_dynamic(work)
        cols = list(feats.columns)

    if len(feats) == 0:
        raise ValueError("No valid rows after cleaning.")
    if len(feats) == 1:
        logger.warning(
            "Only 1 row after feature cleaning — will duplicate before train/validation split; "
            "metrics will be unreliable."
        )
    if len(feats) < 10:
        logger.warning(
            "Only %s training rows — metrics are unreliable; add more data for production quality.",
            len(feats),
        )

    return feats, cols


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
                "message_length": rng.integers(10, 500, n),
                "has_exception": rng.integers(0, 2, n),
                "has_timeout": rng.integers(0, 2, n),
                "has_connection_error": rng.integers(0, 2, n),
                "level": rng.integers(0, 5, n),
                "service_hash": rng.integers(0, 1000, n),
            }
        )
        x_all, feature_columns = _coerce_features(syn)
        x_all = x_all.to_numpy(dtype=np.float64, copy=False)
    else:
        try:
            df = pd.read_csv(features_path)
        except Exception as e:
            logger.exception("Failed reading CSV %s", features_path)
            raise RuntimeError(f"Could not read training CSV: {e}") from e
        feats_df, feature_columns = _coerce_features(df)
        x_all = feats_df.to_numpy(dtype=np.float64, copy=False)

    # train_test_split needs at least 2 rows; preprocess can leave a single training row when
    # holdout consumes the rest — duplicate so sklearn/split succeeds (metrics still unreliable).
    if x_all.shape[0] < 2:
        logger.warning(
            "Only %s training row(s); duplicating so train/validation split succeeds "
            "(metrics will be unreliable).",
            x_all.shape[0],
        )
        x_all = np.vstack([x_all, x_all])

    rng_split = np.random.RandomState(args.random_state)
    x_train, x_val = train_test_split(
        x_all,
        test_size=0.2,
        random_state=rng_split,
        shuffle=True,
    )

    n_train, n_val = x_train.shape[0], x_val.shape[0]

    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_train)
    x_val = scaler.transform(x_val)

    # IsolationForest max_samples cannot exceed n_train; avoid max(2, n_train) alone when n_train==1.
    max_samples = min(args.max_samples, max(2, n_train), n_train)

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
        "scaler": scaler,
        "feature_columns": feature_columns,
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
