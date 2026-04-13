"""
FraudScorer — Real-time ML inference pipeline for fraud detection.

Loads a trained RandomForestClassifier from disk via joblib, scores a feature
vector, and returns a structured FraudScoreResult with SHAP explanations.
"""
from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import shap

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Risk level thresholds (aligned with system_design_v2.md)
# ---------------------------------------------------------------------------
THRESHOLD_LOW: float = 0.35        # [0.00, 0.35)  → LOW
THRESHOLD_MEDIUM: float = 0.65     # [0.35, 0.65)  → MEDIUM
THRESHOLD_HIGH: float = 0.85       # [0.65, 0.85)  → HIGH
                                    # [0.85, 1.00]  → CRITICAL

MODEL_ARTIFACTS_DIR: Path = Path(__file__).parent.parent / "model" / "artifacts"
REPO_MODEL_ARTIFACTS_DIR: Path = Path(__file__).resolve().parents[4] / "ml" / "artifacts"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ShapFeature:
    """Single SHAP feature contribution."""
    feature_name: str
    shap_value: float
    feature_value: float


@dataclass
class FraudScoreResult:
    """Complete inference result returned for a single transaction."""
    fraud_score: float                          # P(fraud) in [0, 1]
    risk_level: str                             # LOW | MEDIUM | HIGH | CRITICAL
    predicted_class: str                        # LEGITIMATE | FRAUD
    top_5_shap_features: list[ShapFeature]     # Top-5 features by |SHAP|
    model_version: str                          # e.g. "v1.0.0"
    inference_latency_ms: float                 # wall-clock latency


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class FraudScorer:
    """
    Singleton-style inference engine that wraps a trained RandomForestClassifier.

    Parameters
    ----------
    model_path:
        Explicit path to the .joblib model file. If None, the scorer
        looks for the latest model in MODEL_ARTIFACTS_DIR.
    """

    def __init__(self, model_path: Optional[str] = None) -> None:
        self._model = None
        self._explainer: Optional[shap.TreeExplainer] = None
        self._model_version: str = "unknown"
        self._feature_names: list[str] = []
        self._load_model(model_path)

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model(self, model_path: Optional[str]) -> None:
        """Load model from disk. Falls back to a stub if no model exists yet."""
        resolved_path = self._resolve_model_path(model_path)
        if resolved_path is None:
            logger.warning(
                "FraudScorer: No model artifact found. "
                "Scorer will return default 0.0 scores until a model is trained."
            )
            return

        try:
            artifact = joblib.load(resolved_path)
            # Artifact may be a raw model or a dict with metadata
            if isinstance(artifact, dict):
                self._model = artifact["model"]
                self._model_version = artifact.get("version", "unknown")
                self._feature_names = artifact.get("feature_names", [])
            else:
                self._model = artifact
                self._model_version = resolved_path.stem

            # Avoid multiprocessing permission failures on restricted Windows setups.
            self._force_single_thread_model()

            # Build SHAP TreeExplainer once on load for speed
            self._explainer = shap.TreeExplainer(self._model)
            logger.info(
                "FraudScorer: loaded model version=%s from %s",
                self._model_version,
                resolved_path,
            )
        except Exception as exc:
            logger.error("FraudScorer: failed to load model — %s", exc)
            self._model = None
            self._explainer = None

    def _force_single_thread_model(self) -> None:
        if self._model is None:
            return
        try:
            if hasattr(self._model, "set_params"):
                self._model.set_params(n_jobs=1)
            elif hasattr(self._model, "n_jobs"):
                self._model.n_jobs = 1
        except Exception as exc:
            logger.warning("FraudScorer: unable to force n_jobs=1 - %s", exc)

    def _resolve_model_path(self, model_path: Optional[str]) -> Optional[Path]:
        """Return Path to model file, picking latest in artifacts dir if not specified."""
        if model_path:
            p = Path(model_path)
            return p if p.exists() else None

        configured_dir = os.getenv("MODEL_ARTIFACTS_DIR")
        candidate_dirs = (
            [Path(configured_dir)] if configured_dir else [MODEL_ARTIFACTS_DIR, REPO_MODEL_ARTIFACTS_DIR]
        )

        candidates: list[Path] = []
        for artifacts_dir in candidate_dirs:
            if artifacts_dir.exists():
                candidates.extend(artifacts_dir.glob("*.joblib"))

        if not candidates:
            return None

        candidates.sort(key=lambda p: p.stat().st_mtime)
        return candidates[-1]

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score(self, feature_vector: list[float], feature_names: Optional[list[str]] = None) -> FraudScoreResult:
        """
        Score a single feature vector.

        Parameters
        ----------
        feature_vector:
            Ordered list of floats as produced by FeatureVector.to_array().
        feature_names:
            Optional ordered list of feature names for SHAP labelling.

        Returns
        -------
        FraudScoreResult
        """
        t_start = time.perf_counter()

        # Fallback when no model is loaded
        if self._model is None:
            latency = (time.perf_counter() - t_start) * 1000
            return FraudScoreResult(
                fraud_score=0.0,
                risk_level="LOW",
                predicted_class="LEGITIMATE",
                top_5_shap_features=[],
                model_version=self._model_version,
                inference_latency_ms=round(latency, 3),
            )

        x = np.array(feature_vector, dtype=np.float64).reshape(1, -1)

        # Predict probability of fraud (class index 1)
        try:
            proba = self._model.predict_proba(x)[0]
        except Exception as exc:
            logger.warning("FraudScorer: predict_proba failed, returning safe fallback - %s", exc)
            latency = (time.perf_counter() - t_start) * 1000
            return FraudScoreResult(
                fraud_score=0.0,
                risk_level="LOW",
                predicted_class="LEGITIMATE",
                top_5_shap_features=[],
                model_version=self._model_version,
                inference_latency_ms=round(latency, 3),
            )
        fraud_score: float = float(proba[1]) if len(proba) > 1 else float(proba[0])

        # Risk level classification
        risk_level = self._classify_risk(fraud_score)
        predicted_class = "FRAUD" if fraud_score >= THRESHOLD_MEDIUM else "LEGITIMATE"

        # SHAP explanation
        top_shap = self._compute_shap(x, feature_names or self._feature_names)

        latency_ms = (time.perf_counter() - t_start) * 1000

        return FraudScoreResult(
            fraud_score=round(fraud_score, 6),
            risk_level=risk_level,
            predicted_class=predicted_class,
            top_5_shap_features=top_shap,
            model_version=self._model_version,
            inference_latency_ms=round(latency_ms, 3),
        )

    def _classify_risk(self, score: float) -> str:
        if score >= THRESHOLD_HIGH:
            return "CRITICAL"
        if score >= THRESHOLD_MEDIUM:
            return "HIGH"
        if score >= THRESHOLD_LOW:
            return "MEDIUM"
        return "LOW"

    def _compute_shap(
        self,
        x: "np.ndarray",
        feature_names: list[str],
    ) -> list[ShapFeature]:
        """Compute SHAP values and return top-5 features by absolute contribution."""
        if self._explainer is None:
            return []
        try:
            shap_values = self._explainer.shap_values(x)
            # shap_values is (n_classes, n_samples, n_features) for RandomForest
            # Take fraud class values (index 1 if binary)
            if isinstance(shap_values, list) and len(shap_values) > 1:
                fraud_shap = shap_values[1][0]
            elif isinstance(shap_values, np.ndarray) and shap_values.ndim == 3:
                fraud_shap = shap_values[0, :, 1]
            else:
                fraud_shap = np.array(shap_values).flatten()

            n_features = len(fraud_shap)
            names = feature_names if len(feature_names) == n_features else [f"f{i}" for i in range(n_features)]
            x_flat = x.flatten()

            indexed = sorted(
                range(n_features),
                key=lambda i: abs(float(fraud_shap[i])),
                reverse=True,
            )
            top5 = indexed[:5]

            return [
                ShapFeature(
                    feature_name=names[i],
                    shap_value=round(float(fraud_shap[i]), 6),
                    feature_value=round(float(x_flat[i]), 6),
                )
                for i in top5
            ]
        except Exception as exc:
            logger.warning("FraudScorer: SHAP computation failed — %s", exc)
            return []

    # ------------------------------------------------------------------
    # Model reload (for hot-swap)
    # ------------------------------------------------------------------

    def reload(self, model_path: Optional[str] = None) -> None:
        """Hot-reload the model from disk without restarting the process."""
        self._load_model(model_path)


# ---------------------------------------------------------------------------
# Module-level singleton for import convenience
# ---------------------------------------------------------------------------
_default_scorer: Optional[FraudScorer] = None


def get_scorer() -> FraudScorer:
    """Return the module-level FraudScorer singleton, creating it if needed."""
    global _default_scorer
    if _default_scorer is None:
        _default_scorer = FraudScorer()
    return _default_scorer
