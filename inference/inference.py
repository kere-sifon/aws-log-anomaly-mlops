"""
SageMaker realtime inference handlers for the scikit-learn Isolation Forest model.

Feature names are centralized in ``expected_features``; at load time order may follow
``feature_columns`` inside ``model.joblib`` (see ``training/train.py``).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Mapping, Union

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)

# Default schema for JSON ``instances`` (adjust when training features change).
expected_features = [
    "cpu_usage",
    "memory_usage",
    "error_rate",
    "request_latency_ms",
    "log_level_encoded",
]

# Filled in model_fn from the training artifact when present (may include e.g. ``timestamp``).
_FEATURE_ORDER: list[str] | None = None

JSON_CONTENT = "application/json"


def model_fn(model_dir: str) -> IsolationForest:
    """Load ``model.joblib`` and return the fitted Isolation Forest."""
    global _FEATURE_ORDER
    path = f"{model_dir.rstrip('/')}/model.joblib"
    logger.info("Loading model artifact from %s", path)
    payload = joblib.load(path)
    if isinstance(payload, dict) and "model" in payload:
        order = payload.get("feature_columns")
        if isinstance(order, list) and order:
            _FEATURE_ORDER = [str(c) for c in order]
            logger.info("Using feature order from artifact (%s columns).", len(_FEATURE_ORDER))
        clf = payload["model"]
    else:
        _FEATURE_ORDER = list(expected_features)
        clf = payload
    if not isinstance(clf, IsolationForest):
        logger.warning("Expected IsolationForest; got %s", type(clf))
    return clf  # type: ignore[return-value]


def _feature_order() -> list[str]:
    return _FEATURE_ORDER if _FEATURE_ORDER else list(expected_features)


def input_fn(request_body: Union[bytes, str], content_type: str) -> pd.DataFrame:
    """Parse ``application/json`` with an ``instances`` array into a feature DataFrame."""
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct not in (JSON_CONTENT, "text/json"):
        raise ValueError(
            f"Unsupported content type {content_type!r}; only {JSON_CONTENT} requests are accepted."
        )

    raw = request_body if isinstance(request_body, str) else request_body.decode("utf-8")
    try:
        parsed: Mapping[str, Any] = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON body: %s", e)
        raise ValueError("Request body must be valid JSON.") from e

    if not isinstance(parsed, dict) or "instances" not in parsed:
        raise ValueError("JSON payload must be an object with an 'instances' array.")

    rows = parsed["instances"]
    if not isinstance(rows, list):
        raise ValueError("'instances' must be a JSON array.")

    df = pd.DataFrame(rows)
    required = _feature_order()

    missing_cols = [c for c in required if c not in df.columns]
    if "timestamp" in required and "timestamp" in missing_cols:
        df["timestamp"] = time.time()
        missing_cols = [c for c in required if c not in df.columns]

    if missing_cols:
        msg = (
            f"Missing feature column(s): {missing_cols}. "
            f"Expected columns: {required}."
        )
        logger.error(msg)
        raise ValueError(msg)

    extra = [c for c in df.columns if c not in required]
    if extra:
        logger.warning("Ignoring unexpected input columns: %s", extra)
    out = df.reindex(columns=required)
    for col in required:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if out.isnull().any().any():
        bad = out[out.isnull().any(axis=1)]
        msg = f"Non-numeric or missing values in features for {len(bad)} instance(s)."
        logger.error(msg)
        raise ValueError(msg)

    return out.astype(np.float64)


def predict_fn(input_data: pd.DataFrame, model: IsolationForest) -> dict[str, np.ndarray]:
    """Return anomaly scores (-1/1 labels) from decision function and predict."""
    arr = input_data.to_numpy(dtype=np.float64, copy=False)
    scores = model.decision_function(arr)
    labels = model.predict(arr)
    return {
        "anomaly_scores": scores,
        "predictions": labels,
    }


def output_fn(prediction: dict[str, np.ndarray], accept: str) -> tuple[str, str]:
    """Serialize per-instance results to JSON when client accepts application/json."""
    accept_l = (accept or JSON_CONTENT).split(";")[0].strip().lower()
    if accept_l not in (JSON_CONTENT, "text/json", "*/*"):
        raise ValueError(f"Unsupported Accept type {accept!r}; use {JSON_CONTENT}.")

    scores = np.asarray(prediction["anomaly_scores"], dtype=float)
    preds = np.asarray(prediction["predictions"], dtype=int)
    out_rows = []
    for s, p in zip(scores.tolist(), preds.tolist()):
        out_rows.append(
            {
                "anomaly_score": float(s),
                "is_anomaly": bool(p == -1),
            }
        )
    body = {"predictions": out_rows}
    return json.dumps(body), JSON_CONTENT
