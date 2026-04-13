"""
train_stub.py — Creates a minimal RandomForest stub model for local development.

Run once to produce a .joblib artifact so FraudScorer can load a model
before a real training run has been executed.

Usage
-----
    cd backend
    python -m app.ml.model.train_stub
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the backend directory is on sys.path
BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from app.ml.features.engineer import FeatureVector

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_PATH = ARTIFACTS_DIR / "rf_v0.0.1_stub.joblib"

FEATURE_NAMES = FeatureVector().feature_names
N_FEATURES = len(FEATURE_NAMES)


def main() -> None:
    print(f"Training stub RandomForest with {N_FEATURES} features …")
    rng = np.random.default_rng(42)

    # Generate synthetic training data (1000 samples, 5% fraud)
    n_samples = 1000
    X = rng.standard_normal((n_samples, N_FEATURES))
    y = (rng.random(n_samples) < 0.05).astype(int)

    clf = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)
    clf.fit(X, y)

    artifact = {
        "model": clf,
        "version": "v0.0.1-stub",
        "feature_names": FEATURE_NAMES,
    }
    joblib.dump(artifact, OUTPUT_PATH)
    print(f"Stub model saved → {OUTPUT_PATH}")
    print("FraudScorer will auto-pick this on next startup.")


if __name__ == "__main__":
    main()
