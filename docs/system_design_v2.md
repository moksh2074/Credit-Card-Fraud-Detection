# Credit Card Fraud Detection Platform
## Complete System Design, Feature List, Logic Map & UI/UX Design System
**Senior Architect & Design Reference Document — Production Grade**

**Document Scope:** This document covers the complete system architecture, feature specifications, logic flows, data pipelines, ML design, SIEM integration, cloud topology, and the global UI/UX design system for a production-grade Credit Card Fraud Detection Platform. No implementation code is included. This document is the authoritative reference for all engineering, ML, security, and frontend design teams.

**v2 Changes:** External payment gateway simulator removed from all workflow references. Transaction data originates exclusively from the internal Synthetic Transaction Generator. A full UI/UX Design System (Section 10) has been integrated to govern all frontend visual decisions.

---

## TABLE OF CONTENTS
1. Complete Feature List
2. System Logic Flow (End-to-End)
3. ML Logic Map
4. SIEM / Wazuh Logic Map
5. Dashboard Analytics Logic
6. Data Flow Architecture
7. Technology Mapping
8. Advanced Features
9. System Constraints & Non-Functional Requirements
10. UI/UX Design System

---

## SECTION 1 — COMPLETE FEATURE LIST

### 1.1 USER MANAGEMENT FEATURES
* **Feature: User Registration**
  * Purpose: Allow analysts, admins, and auditors to create platform accounts with role-based access.
  * Input: Name, email, password, role (admin / analyst / auditor / read-only), organization ID.
  * Output: New user record in IBM Cloud DB, JWT token issued, confirmation email sent via IBM Cloud Notifications.
* **Feature: User Authentication (JWT-based)**
  * Purpose: Secure stateless authentication for API access and frontend session management.
  * Input: Email, password.
  * Output: Signed JWT access token (short TTL) + refresh token (long TTL), stored securely in HTTP-only cookies.
* **Feature: Role-Based Access Control (RBAC)**
  * Purpose: Enforce least-privilege access across all platform features.
  * Input: User role assigned at registration or modified by admin.
  * Output: Permission matrix enforced on every API route and frontend component. Admin sees all; Analyst sees dashboards + logs; Auditor has read-only access to reports.
* **Feature: Session Management & Token Refresh**
  * Purpose: Maintain secure, uninterrupted user sessions without requiring re-login on short expiry.
  * Input: Refresh token from secure cookie.
  * Output: New access token issued; old token blacklisted in the token revocation store.
* **Feature: Password Reset & Recovery**
  * Purpose: Allow users to recover account access securely.
  * Input: Registered email address.
  * Output: Time-limited one-time reset link delivered via IBM Cloud Notifications email channel.
* **Feature: Multi-Factor Authentication (MFA)**
  * Purpose: Add a second layer of identity verification for high-privilege users.
  * Input: TOTP code from authenticator app or SMS OTP.
  * Output: MFA verification status recorded; session elevated to fully authenticated state.
* **Feature: Audit Trail for User Actions**
  * Purpose: Track every significant user action for compliance and forensic review.
  * Input: Every API call made by an authenticated user.
  * Output: Structured log entry written to IBM Cloud DB and forwarded to Wazuh, capturing user ID, action type, affected resource, timestamp, and IP address.

### 1.2 TRANSACTION PROCESSING FEATURES
* **Feature: Real-Time Transaction Ingestion (API Endpoint)**
  * Purpose: Accept incoming transaction data produced by the internal Synthetic Transaction Generator and feed it into the full processing pipeline.
  * Input: JSON payload — transaction ID, card number (hashed), merchant ID, merchant category code (MCC), amount, currency, timestamp, device ID, IP address, geolocation (lat/lon), channel (online/POS/ATM).
  * Output: Transaction persisted to the primary transaction store; message queued for ML inference pipeline.
* **Feature: Synthetic Transaction Generator**
  * Purpose: The sole and exclusive source of transaction data. Simulates realistic transaction streams for real-time demonstration, testing, and model validation without using real cardholder data. There is no external payment gateway or third-party simulator involved. All transaction events originate here.
  * Input: Configuration parameters — transactions per second (TPS), fraud injection rate (%), cardholder profiles, merchant profiles, geo distribution settings, time-of-day weighting, MCC distribution, device type ratios.
  * Output: Continuous stream of synthetic transaction payloads delivered directly to the backend ingestion API endpoint (`/api/v1/transactions/ingest`), mimicking realistic distributions of amounts, times, locations, and merchant categories.
  * Fraud Injection Logic: The generator has a built-in fraud scenario engine that injects configurable patterns — velocity bursts, impossible travel, card testing micro-transactions, high-value CNP events — at the configured fraud injection rate. This ensures the full detection pipeline is exercised during simulation.
* **Feature: Generator Configuration Panel (Admin)**
  * Purpose: Allow administrators to control the behavior of the Synthetic Transaction Generator at runtime without restarting the service.
  * Input: Target TPS, fraud injection rate (%), active fraud scenario types (checkboxes), cardholder segment distribution, geo bias settings.
  * Output: Updated generator configuration applied immediately; generation metrics (current TPS, fraud events/min, queue depth) displayed in the admin dashboard panel.
* **Feature: Transaction Normalization & Enrichment**
  * Purpose: Standardize raw transaction data and augment it with derived features required by the ML model.
  * Input: Raw transaction payload from the Synthetic Generator.
  * Output: Normalized transaction object with enriched fields.
* **Feature: Transaction Deduplication**
  * Purpose: Prevent duplicate transaction records from being processed and stored.
  * Input: Incoming transaction ID + cardholder ID + timestamp.
  * Output: Duplicate records rejected with 409 Conflict status.
* **Feature: Batch Transaction Processing (Historical Replay)**
  * Purpose: Allow administrators to replay previously generated synthetic transaction batches through the ML model.
  * Input: Date range, cardholder segment, or archived CSV.
  * Output: Batch inference results written to analysis table.
* **Feature: Transaction Status Lifecycle Management**
  * Purpose: Track the processing state of every transaction through the system pipeline.
  * Output: Status field updated at each stage — RECEIVED → ENRICHED → SCORED → LOGGED → ALERTED → RESOLVED.

### 1.3 FRAUD DETECTION FEATURES (ML-BASED)
* **Feature: Real-Time ML Inference (Random Forest)**
  * Purpose: Score each incoming transaction for fraud probability using a trained Random Forest classifier.
  * Output: Fraud probability score (0.0–1.0), predicted class label, top contributing features (SHAP values).
* **Feature: Feature Engineering Pipeline**
  * Purpose: Transform raw transaction fields into a structured, model-ready feature vector.
* **Feature: Risk Level Classification**
  * Output: Risk tier label — LOW (0.0–0.35), MEDIUM (0.35–0.65), HIGH (0.65–0.85), CRITICAL (0.85–1.00).
* **Feature: Model Versioning & Registry**
  * Purpose: Manage multiple trained model versions in IBM Cloud Object Storage.
* **Feature: Model Retraining Pipeline**
  * Purpose: Periodically retrain the Random Forest model on fresh data.
* **Feature: Model Drift Monitoring**
  * Purpose: Detect when the production model's performance degrades (PSI).
* **Feature: SHAP Explainability**
  * Output: SHAP values per feature, ranked contribution list.
* **Feature: Threshold Tuning Interface**
  * Purpose: Allow authorized users to adjust fraud score thresholds.

### 1.4 RULE-BASED DETECTION FEATURES (SIEM / WAZUH)
* **Feature: Structured Log Forwarding to Wazuh**
  * Purpose: Stream all transaction logs and fraud score results to the Wazuh SIEM manager.
* **Feature: Transaction Velocity Rule**
  * Detect rapid successive transactions from the same card.
* **Feature: Geographic Impossibility Rule**
  * Detect when a card is used at two geographically distant locations physically impossible time frame.
* **Feature: Anomalous Amount Rule**
  * Flag transactions that deviate significantly from baseline.
* **Feature: High-Risk Merchant Category Rule**
* **Feature: Card-Not-Present (CNP) High-Value Rule**
* **Feature: Multiple Declines Then Approval Rule**
* **Feature: New Device + High-Risk Transaction Rule**
* **Feature: Wazuh Custom Rule Management**

### 1.5 LOGGING & MONITORING FEATURES
* **Feature: Structured Transaction Log Generation**
  * Produce a complete, machine-readable audit record (JSON).
* **Feature: Application Performance Monitoring (APM)**
* **Feature: Log Archival to IBM Cloud Object Storage**
* **Feature: Log Integrity Verification** (SHA-256 hashes)
* **Feature: System Health Monitoring**

### 1.6 ALERTING & NOTIFICATION FEATURES
* **Feature: Real-Time Fraud Alert Generation**
* **Feature: Alert Severity Classification** (P0-P3)
* **Feature: Alert Deduplication & Suppression**
* **Feature: Webhook-Based Alert Delivery**
* **Feature: Email Alert Delivery via IBM Cloud Notifications**
* **Feature: Alert Acknowledgment & Resolution Workflow**

### 1.7 DASHBOARD & ANALYTICS FEATURES
* **Feature: Real-Time Fraud Activity Feed** (SSE powered)
* **Feature: Fraud Rate Trend Chart**
* **Feature: Risk Distribution Histogram**
* **Feature: Geographic Fraud Heatmap**
* **Feature: Merchant Category Analysis Panel**
* **Feature: Device & Channel Analysis**
* **Feature: Time-of-Day / Day-of-Week Anomaly Chart**
* **Feature: Alert Management Dashboard**
* **Feature: ML Model Performance Dashboard**
* **Feature: Custom Report Builder**

### 1.8 CLOUD INTEGRATION FEATURES
* **IBM Cloud Object Storage:** Log Archival & Model Registry.
* **IBM Cloud Notifications:** Alert Dispatch.
* **IBM Cloud DB:** Operational Data Store (PostgreSQL).

### 1.9 SECURITY FEATURES
* API Request Authentication & Authorization (JWT).
* Input Validation & Sanitization (Pydantic).
* Card Data Masking & Tokenization (SHA-256 hashing).
* Secrets Management.
* Rate Limiting & DDoS Protection.
* HTTPS / TLS Enforcement.
* Database Encryption at Rest.

### 1.10 PERFORMANCE & SCALABILITY FEATURES
* Asynchronous ML Inference Queue (Celery/Redis).
* Inference Response Caching (Redis).
* Horizontal Scaling for Backend Services.
* Database Query Optimization & Indexing.

---

## SECTION 2 — SYSTEM LOGIC FLOW (END-TO-END)

**STEP 1 — Transaction Originates from Synthetic Generator**
Source: Internal Synthetic Transaction Generator (the sole data source).
Generates JSON payloads and posts to `/api/v1/transactions/ingest`. Injects fraud scenarios based on configuration.

**STEP 2 — API Gateway / Backend Receives Request**
Rate limiting -> JWT Auth -> Schema Validation -> PAN Hashing -> Deduplication. Writes to DB as RECEIVED.

**STEP 3 — Transaction Enrichment**
Calculates Temporal, Amount, Velocity, Geo, Device, and Behavioral features. Status -> ENRICHED. Queues for ML.

**STEP 4 — ML Inference**
Random Forest inference via worker. Computes probability, extracts SHAP, assigns risk tier. Status -> SCORED.

**STEP 5 — Structured Log Generation**
JSON log written to IBM Cloud DB, IBM COS, and local Wazuh forwarder file. Status -> LOGGED.

**STEP 6 — Wazuh SIEM Analysis**
Wazuh agent reads logs, evaluates rules, generates alerts.

**STEP 7 — Alert Generation & Routing**
Backend receives Wazuh alerts and ML CRITICAL scores, dedupes, classifies severity, dispatches via IBM Cloud Notifications. Status -> ALERTED.

**STEP 8 — Dashboard Display**
SSE pushes updates to React frontend.

**STEP 9 — Analyst Review & Resolution**

---

## SECTION 3 — ML LOGIC MAP
* **Training Data:** Kaggle Credit Card Fraud Detection Dataset.
* **Algorithm:** scikit-learn RandomForestClassifier.
* **Features:** Amount logs, temporal sine/cosine, rolling velocities (1h, 6h, 24h), Haversine distances.
* **Thresholds:** LOW (0-0.34), MEDIUM (0.35-0.64), HIGH (0.65-0.84), CRITICAL (0.85-1.00).

---

## SECTION 4 — SIEM / WAZUH LOGIC MAP
* **Ingestion:** NDJSON file read by Wazuh agent.
* **Rules:** ML Score Thresholds, Velocity bursts, Geographic impossibilities, Amount anomalies, Device flags.

---

## SECTION 5 — DASHBOARD ANALYTICS LOGIC
Pre-aggregated backend API serving sub-200ms query results for Recharts visualization.

---

## SECTION 6 — DATA FLOW ARCHITECTURE
* **API Ingestion:** FastAPI
* **Inference Queue:** Celery + Redis
* **Database:** IBM Cloud DB (PostgreSQL)
* **Storage:** IBM Cloud Object Storage

---

## SECTION 7 — TECHNOLOGY MAPPING
* Frontend: Vite, React, Tailwind, Recharts, Zustand.
* Backend: Python, FastAPI, SQLAlchemy async, Celery, Redis.
* ML: scikit-learn, joblib, SHAP.
* SIEM: Wazuh.

---

## SECTION 8, 9 — ADVANCED FEATURES & CONSTRAINTS
* Target Inference Latency: < 100ms p95.
* Target API Response: < 200ms p95.
* Unsupervised anomaly detection, graph network analysis, behavioral baselines.

---

## SECTION 10 — UI/UX DESIGN SYSTEM

**10.1 COLOR SYSTEM**
* Primary Color (Color A): Electric Indigo `#6366F1`
* Alert Color (Color B): Crimson Red `#EF4444`
* Background Base: Deep Navy `#0B0F1A`
* Card Surface: Dark Slate `#111827`
* Elevated Card: Elevated Slate `#1A2236`

**10.2 TYPOGRAPHY**
* Primary Font: Inter
* Monospace Font: JetBrains Mono

**10.6 GLASSMORPHISM CARD SYSTEM**
* Standard: `rgba(17, 24, 39, 0.6)` with backdrop blur.
* Elevated: `rgba(26, 34, 54, 0.75)` with indigo border tint.

*(Refer to CSS styles implemented in globals.css for full token mappings).*

End of Document