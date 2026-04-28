"""
SageMaker realtime inference handlers for the scikit-learn Isolation Forest model.

Accepts the same log-content feature schema as ai-monitoring-ml-service so the
SageMaker endpoint can serve as a drop-in replacement for the FastAPI ML service.

Request format (application/json):
    {
        "instances": [
            {
                "log_id": "abc-123",          // optional, echoed in response
                "features": {
                    "message_length": 142,
                    "level": "ERROR",          // string or int 0-4
                    "service": "payment-svc",  // hashed to int internally
                    "has_exception": true,
                    "has_timeout": false,
                    "has_connection_error": false
                }
            }
        ]
    }

Response format (application/json):
    {
        "predictions": [
            {
                "log_id": "abc-123",
                "is_anomaly": true,
                "anomaly_score": 0.83,
                "confidence": 0.66
            }
        ]
    }
"""

from __future__ import annotations

import json
import logging
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

LEVEL_MAPPING = {"DEBUG": 0, "INFO": 1, "WARN": 2, "WARNING": 2, "ERROR": 3, "FATAL": 4, "CRITICAL": 4}

FEATURE_COLUMNS = [
    "message_length",
    "has_exception",
    "has_timeout",
    "has_connection_error",
    "level",
    "service_hash",
]

JSON_CONTENT = "application/json"

_MODEL: IsolationForest | None = None
_SCALER: StandardScaler | None = None
_THRESHOLD: float | None = None


def model_fn(model_dir: str) -> IsolationForest:
    """Load model.joblib and populate the scaler and threshold globals."""
    global _MODEL, _SCALER, _THRESHOLD
    path = f"{model_dir.rstrip('/')}/model.joblib"
    logger.info("Loading model artifact from %s", path)
    payload = joblib.load(path)
    if isinstance(payload, dict):
        _MODEL = payload["model"]
        _SCALER = payload.get("scaler")
        _THRESHOLD = payload.get("threshold")
    else:
        _MODEL = payload
    if not isinstance(_MODEL, IsolationForest):
        logger.warning("Expected IsolationForest; got %s", type(_MODEL))
    if _SCALER is None:
        logger.warning("No scaler found in model artifact; scores may differ from training.")
    return _MODEL


def _encode_features(raw: dict[str, Any]) -> list[float]:
    """Convert a single log features dict to the canonical numeric vector."""
    msg_len = float(raw.get("message_length", 0))
    has_exc = float(bool(raw.get("has_exception", False)))
    has_to = float(bool(raw.get("has_timeout", False)))
    has_ce = float(bool(raw.get("has_connection_error", False)))

    level_raw = raw.get("level", "INFO")
    if isinstance(level_raw, (int, float)):
        level = float(level_raw)
    else:
        level = float(LEVEL_MAPPING.get(str(level_raw).upper(), 1))

    service = str(raw.get("service", "unknown"))
    service_hash = float(hash(service) % 1000)

    return [msg_len, has_exc, has_to, has_ce, level, service_hash]


def input_fn(request_body: bytes | str, content_type: str) -> dict:
    """Parse request JSON into feature matrix and log_ids."""
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct not in (JSON_CONTENT, "text/json"):
        raise ValueError(f"Unsupported content type {content_type!r}; only {JSON_CONTENT} is accepted.")

    raw = request_body if isinstance(request_body, str) else request_body.decode("utf-8")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError("Request body must be valid JSON.") from e

    if not isinstance(parsed, dict) or "instances" not in parsed:
        raise ValueError("JSON payload must be an object with an 'instances' array.")

    instances = parsed["instances"]
    if not isinstance(instances, list) or not instances:
        raise ValueError("'instances' must be a non-empty JSON array.")

    log_ids = []
    rows = []
    for inst in instances:
        log_ids.append(inst.get("log_id", ""))
        features_raw = inst.get("features", inst)
        rows.append(_encode_features(features_raw))

    x = np.array(rows, dtype=np.float64)
    return {"features": x, "log_ids": log_ids}


def predict_fn(input_data: dict, model: IsolationForest) -> dict:
    """Scale features, run the model, and compute confidence scores."""
    x = input_data["features"]
    log_ids = input_data["log_ids"]

    if _SCALER is not None:
        x = _SCALER.transform(x)

    raw_scores = model.score_samples(x)
    labels = model.predict(x)

    # Mirror ai-monitoring-ml-service: sigmoid of raw score → anomaly_score (0-1, higher = more anomalous).
    anomaly_scores = 1.0 / (1.0 + np.exp(raw_scores))
    # Confidence = how far the score is from the decision boundary (0.5).
    confidence = np.abs(anomaly_scores - 0.5) * 2.0

    return {
        "log_ids": log_ids,
        "is_anomaly": (labels == -1).tolist(),
        "anomaly_scores": anomaly_scores.tolist(),
        "confidence": confidence.tolist(),
    }


def output_fn(prediction: dict, accept: str) -> tuple[str, str]:
    """Serialize per-instance results to JSON."""
    accept_l = (accept or JSON_CONTENT).split(";")[0].strip().lower()
    if accept_l not in (JSON_CONTENT, "text/json", "*/*"):
        raise ValueError(f"Unsupported Accept type {accept!r}; use {JSON_CONTENT}.")

    out_rows = []
    for log_id, is_anom, score, conf in zip(
        prediction["log_ids"],
        prediction["is_anomaly"],
        prediction["anomaly_scores"],
        prediction["confidence"],
    ):
        row: dict[str, Any] = {
            "is_anomaly": bool(is_anom),
            "anomaly_score": float(score),
            "confidence": float(conf),
        }
        if log_id:
            row["log_id"] = log_id
        out_rows.append(row)

    return json.dumps({"predictions": out_rows}), JSON_CONTENT
