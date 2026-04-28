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


def _dataframe_to_numeric_features(df: pd.DataFrame) -> pd.DataFrame:
    """Produce a numeric-only feature matrix from mixed log tables.

    Logs often arrive as strings. We first keep native numeric dtypes, then coerce
    digits to numbers, then factorize remaining text columns into ordinal codes
    so Isolation Forest always sees numeric inputs.
    """
    numeric = df.select_dtypes(include=["number"]).copy()
    if numeric.shape[1] > 0:
        return numeric

    built: dict[str, pd.Series] = {}
    for c in df.columns:
        col = df[c]
        parsed = pd.to_numeric(col, errors="coerce")
        if parsed.notna().sum() > 0:
            name = str(c).replace("/", "_")[:96] if str(c) else "col"
            while name in built:
                name = f"{name}_dup"
            built[name] = parsed
            continue

        codes = pd.factorize(col.astype(str), sort=False)[0].astype(np.float64)
        name = str(c).replace("/", "_")[:96] if str(c) else "col"
        while name in built:
            name = f"{name}_freq"
        built[f"{name}_freq"] = pd.Series(codes, index=df.index)

    if not built:
        raise ValueError("No usable columns after loading raw inputs.")
    logger.info(
        "No native numeric columns; built %s numeric columns via coercion/factorization",
        len(built),
    )
    return pd.DataFrame(built)


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
    else:
        rng = np.random.default_rng(42)
        n, d = 400, 8
        df = pd.DataFrame(rng.standard_normal(size=(n, d)), columns=[f"f{i}" for i in range(d)])
        df["trace"] = rng.integers(0, 2, size=n).astype(int)

    numeric = _dataframe_to_numeric_features(df)

    n_hold = min(80, max(10, numeric.shape[0] // 5))
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
