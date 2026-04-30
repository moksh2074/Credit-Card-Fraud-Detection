import json
import random
import time
import uuid
from datetime import datetime

OUTPUT_FILE = r"D:\ibm_splunk\fraud_logs.json"

countries = ["IN", "US", "GB", "AU"]
channels = ["ONLINE", "POS", "ATM"]
device_types = ["mobile", "desktop", "pos", "atm"]

def generate_log():
    fraud = random.choice([True, False, False])  # more legit than fraud

    amount = round(random.uniform(1, 15000), 2)
    velocity_1h = random.randint(0, 5)
    geo_distance = random.uniform(0, 15000)

    log = {
        "log_id": str(uuid.uuid4()),
        "event_type": "fraud_score_result",
        "timestamp": datetime.utcnow().isoformat(),
        "transaction_id": str(uuid.uuid4()),
        "card_id_hash": f"card_{random.randint(1,100):06}",
        "merchant_id": f"merch_{random.randint(1000,9999)}",
        "amount": amount,
        "currency": "INR",
        "channel": random.choice(channels),
        "geo_country": random.choice(countries),
        "device_type": random.choice(device_types),
        "is_new_device": random.choice([True, False]),
        "velocity_1h": velocity_1h,
        "geo_distance_km": geo_distance,
        "impossible_travel_flag": geo_distance > 5000,
        "fraud_score": round(random.uniform(0,1),2),
        "risk_level": "HIGH" if fraud else "LOW",
        "predicted_class": "FRAUD" if fraud else "LEGITIMATE"
    }

    return log

while True:
    log = generate_log()
    with open(OUTPUT_FILE, "a") as f:
        f.write(json.dumps(log) + "\n")

    time.sleep(1)