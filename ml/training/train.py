import os
import time
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score
from imblearn.over_sampling import SMOTE

# List of 29 features expected by the backend FraudScorer
FEATURE_NAMES = [
    "amount_log", "amount_vs_30d_mean_ratio", "amount_vs_90d_mean_ratio", "is_round_amount",
    "hour_sin", "hour_cos", "day_of_week_sin", "day_of_week_cos", "is_weekend", "is_night",
    "tx_count_1h", "tx_count_6h", "tx_count_24h", "amount_sum_1h", "unique_merchants_24h",
    "unique_geo_clusters_24h", "geo_distance_from_last_km", "implied_speed_kmh",
    "impossible_travel", "is_international", "is_new_device", "device_type_encoded",
    "device_fraud_rate", "merchant_fraud_rate", "mcc_risk_encoded", "is_high_risk_mcc",
    "days_since_last_legit_tx", "card_age_days", "account_standing_encoded"
]

def train_model():
    print("Starting ML Model Training Pipeline (Production Context)...")
    
    # 1. Load Data
    data_path = os.path.join(os.path.dirname(__file__), "../data/raw/creditcard.csv")
    if not os.path.exists(data_path):
        print(f"Error: Dataset not found at {data_path}.")
        return
        
    print("Reading dataset...")
    # Read only first 100,000 rows to speed up check while remaining representative
    df = pd.read_csv(data_path, nrows=100000)
    
    # 2. Minimal Feature Engineering to match FeatureVector shape (29 features)
    print("Engineering features for production compatibility...")
    
    # Create an empty feature Matrix (rows, 29)
    X = np.zeros((len(df), len(FEATURE_NAMES)))
    
    # Map raw columns to FeatureVector positions
    # Position 0: amount_log
    X[:, 0] = np.log1p(df['amt'])
    
    # Position 4 & 5: hour_sin, hour_cos (derived from unix_time)
    dt = pd.to_datetime(df['unix_time'], unit='s')
    hours = dt.dt.hour
    X[:, 4] = np.sin(2 * np.pi * hours / 24)
    X[:, 5] = np.cos(2 * np.pi * hours / 24)
    
    # Position 6 & 7: dow_sin, dow_cos
    dow = dt.dt.dayofweek
    X[:, 6] = np.sin(2 * np.pi * dow / 7)
    X[:, 7] = np.cos(2 * np.pi * dow / 7)
    
    # Position 8: is_weekend
    X[:, 8] = (dow >= 5).astype(int)
    
    y = df['is_fraud']
    
    # 3. Split
    print("Splitting dataset...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # 4. SMOTE
    print(f"Dataset size: {len(X_train)} samples. Applying SMOTE...")
    smote = SMOTE(random_state=42)
    X_train_sm, y_train_sm = smote.fit_resample(X_train, y_train)
    
    # 5. Train Model
    print("Training RandomForestClassifier...")
    clf = RandomForestClassifier(n_estimators=50, random_state=42, class_weight='balanced', n_jobs=-1)
    clf.fit(X_train_sm, y_train_sm)
    
    # 6. Evaluate
    print("Evaluating model...")
    y_pred = clf.predict(X_test)
    y_prob = clf.predict_proba(X_test)[:, 1]
    
    print("\n--- Evaluation Report ---")
    print(f"AUC-ROC:   {roc_auc_score(y_test, y_prob):.4f}")
    print(f"Precision: {precision_score(y_test, y_pred):.4f}")
    print(f"Recall:    {recall_score(y_test, y_pred):.4f}")
    print(f"F1 Score:  {f1_score(y_test, y_pred):.4f}")
    print("-------------------------\n")
    
    # 7. Save Artifacts in Production Dict Format
    artifact_dir = os.path.join(os.path.dirname(__file__), "../artifacts")
    os.makedirs(artifact_dir, exist_ok=True)
    
    timestamp = int(time.time())
    artifact_path = os.path.join(artifact_dir, f"model_v{timestamp}.joblib")
    
    artifact = {
        "model": clf,
        "version": f"v1.0.{timestamp}",
        "feature_names": FEATURE_NAMES
    }
    
    joblib.dump(artifact, artifact_path)
    print(f"Production artifact saved to: {artifact_path}")

if __name__ == "__main__":
    train_model()
