# Model artifacts directory
# Trained RandomForest models are stored here as .joblib files.
# Naming convention: rf_v{major}.{minor}.{patch}.joblib
# The FraudScorer automatically picks the latest file by mtime.
#
# Example artifact bundle (saved by training pipeline):
# {
#   "model": <sklearn RandomForestClassifier>,
#   "version": "v1.0.0",
#   "feature_names": ["amount_log", "amount_vs_30d_mean_ratio", ...]
# }
#
# To generate a stub model for dev/testing run:
#   python backend/app/ml/model/train_stub.py
