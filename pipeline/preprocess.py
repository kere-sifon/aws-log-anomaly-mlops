#!/usr/bin/env python3
"""
SageMaker Processing job: raw log inputs -> numeric feature matrix + labeled holdout for evaluation.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

LEVEL_MAPPING = {"DEBUG": 0, "INFO": 1, "WARN": 2, "WARNING": 2, "ERROR": 3, "FATAL": 4, "CRITICAL": 4}

# Canonical feature columns — must match training/train.py and inference/inference.py.
FEATURE_COLUMNS = [
    "message_length",
    "has_exception",
    "has_timeout",
    "has_connection_error",
    "level",
    "service_hash",
]

LOG_COLUMNS = {"message", "level", "service", "has_exception", "has_timeout", "has_connection_error"}


def _is_log_dataframe(df: pd.DataFrame) -> bool:
    """True when the DataFrame looks like raw log records (has message or level column)."""
    return bool({"message", "level"} & set(df.columns))


def _extract_log_features(df: pd.DataFrame) -> pd.DataFrame:
    """Convert raw log records to the canonical numeric feature matrix.

    Mirrors the feature extraction in ai-monitoring-ml-service so both systems
    train and score on identical signals.
    """
    out = pd.DataFrame(index=df.index)

    msg = df["message"].astype(str) if "message" in df.columns else pd.Series("", index=df.index)
    msg_lower = msg.str.lower()

    out["message_length"] = msg.str.len().fillna(0).astype(int)

    if "has_exception" in df.columns:
        out["has_exception"] = pd.to_numeric(df["has_exception"], errors="coerce").fillna(0).astype(int)
    else:
        out["has_exception"] = msg_lower.str.contains("exception", regex=False).astype(int)

    if "has_timeout" in df.columns:
        out["has_timeout"] = pd.to_numeric(df["has_timeout"], errors="coerce").fillna(0).astype(int)
    else:
        out["has_timeout"] = msg_lower.str.contains("timeout", regex=False).astype(int)

    if "has_connection_error" in df.columns:
        out["has_connection_error"] = pd.to_numeric(df["has_connection_error"], errors="coerce").fillna(0).astype(int)
    else:
        out["has_connection_error"] = (
            msg_lower.str.contains("connection", regex=False) & msg_lower.str.contains("error", regex=False)
        ).astype(int)

    level_col = df["level"].astype(str).str.upper() if "level" in df.columns else pd.Series("INFO", index=df.index)
    out["level"] = level_col.map(LEVEL_MAPPING).fillna(1).astype(int)

    service_col = df["service"].astype(str) if "service" in df.columns else pd.Series("unknown", index=df.index)
    out["service_hash"] = service_col.apply(lambda s: hash(s) % 1000).astype(int)

    return out


def _feature_frame_from_raw(raw_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build training features and a holdout set with a binary ``label`` column (1 = anomaly)."""
    paths = sorted(raw_dir.glob("**/*.csv")) + sorted(raw_dir.glob("**/*.jsonl"))
    if paths:
        frames = []
        for p in paths:
            if p.suffix == ".csv":
                frames.append(pd.read_csv(p))
            else:
                rows = []
                with p.open(encoding="utf-8") as f:
                    for line in f:
                        rows.append(json.loads(line))
                frames.append(pd.DataFrame(rows))
        df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
        numeric = _extract_log_features(df) if _is_log_dataframe(df) else df[FEATURE_COLUMNS].copy()
    else:
        rng = np.random.default_rng(42)
        n = 400
        numeric = pd.DataFrame({
            "message_length": rng.integers(10, 500, n),
            "has_exception": rng.integers(0, 2, n),
            "has_timeout": rng.integers(0, 2, n),
            "has_connection_error": rng.integers(0, 2, n),
            "level": rng.integers(0, 5, n),
            "service_hash": rng.integers(0, 1000, n),
        })
        logger.warning("No raw log files found in %s — using synthetic data for training.", raw_dir)

    n = numeric.shape[0]
    if n == 0:
        raise ValueError("No rows after feature extraction.")
    if n == 1:
        logger.warning(
            "Only 1 row after feature extraction; duplicating so train/holdout split succeeds "
            "(evaluation metrics will be unreliable — add more log lines for realistic training)."
        )
        numeric = pd.concat([numeric, numeric], ignore_index=True)
        n = 2
    # Target ~20% holdout (min 10, max 80) but never exceed available rows minus one
    # for training, otherwise rng.choice raises when n_hold > len(population).
    n_hold = min(80, max(10, n // 5), n - 1)
    rng = np.random.default_rng(7)
    idx = rng.choice(numeric.index, size=n_hold, replace=False)
    holdout = numeric.loc[idx].copy()
    train_df = numeric.drop(idx)

    contamination = 0.05
    scores = train_df.std(axis=1).fillna(0) + train_df.abs().sum(axis=1) * 0.01
    thresh = scores.quantile(1.0 - contamination)
    holdout["label"] = ((holdout.std(axis=1).fillna(0) + holdout.abs().sum(axis=1) * 0.01) > thresh).astype(int)

    return train_df.reset_index(drop=True), holdout.reset_index(drop=True)


def main() -> None:
    raw_dir = Path("/opt/ml/processing/input/raw")
    out = Path("/opt/ml/processing/output")
    holdout_dir = out / "holdout"
    out.mkdir(parents=True, exist_ok=True)
    holdout_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Reading raw inputs from %s", raw_dir)
    features, holdout = _feature_frame_from_raw(raw_dir)

    feat_path = out / "features.csv"
    features.to_csv(feat_path, index=False)
    logger.info("Wrote training features: %s rows -> %s", len(features), feat_path)

    eval_path = holdout_dir / "eval.csv"
    holdout.to_csv(eval_path, index=False)
    logger.info("Wrote labeled holdout: %s rows -> %s", len(holdout), eval_path)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Preprocess failed")
        sys.exit(1)
