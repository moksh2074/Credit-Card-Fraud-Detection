# Credit Card Fraud Detection Platform - API Reference

## Authentication (`/api/v1/auth`)

### `POST /register`
- **Description:** Registers a new user.
- **Request Schema:** `UserCreate` (email, password, role, org_id)
- **Response Schema:** `UserResponse` (id, email, role, is_active, created_at)
- **Authentication:** None

### `POST /login`
- **Description:** Authenticates a user and returns JWT tokens.
- **Request Schema:** `LoginRequest` (email, password)
- **Response Schema:** `Token` (access_token, refresh_token, token_type)
- **Authentication:** None

### `POST /refresh`
- **Description:** Refreshes an expired access token.
- **Request Schema:** `TokenRefreshRequest` (refresh_token)
- **Response Schema:** `Token`
- **Authentication:** Valid Refresh Token

### `POST /logout`
- **Description:** Logs out the current user.
- **Authentication:** Bearer Token

---
## Transactions (`/api/v1/transactions`)

### `POST /ingest`
- **Description:** Ingests a new transaction for fraud scoring.
- **Request Schema:** `TransactionIngestRequest` (transaction_id, card_id_hash, merchant_id, mcc, amount, currency, channel, etc.)
- **Response Schema:** Status Message
- **Authentication:** Bearer Token (System/Service Account)

### `GET /`
- **Description:** Retrieves paginated transactions with optional filtering.
- **Query Parameters:** `risk_level`, `channel`, `start_date`, `end_date`, `page`, `size`
- **Response Schema:** `PaginatedTransactionResponse`
- **Authentication:** Bearer Token (Admin/Analyst)

### `GET /{id}`
- **Description:** Retrieves a specific transaction by ID.
- **Response Schema:** `TransactionResponse`
- **Authentication:** Bearer Token (Admin/Analyst)

---
## Fraud Alerts (`/api/v1/alerts`)

### `GET /`
- **Description:** Retrieves alerts filtered by status and severity.
- **Query Parameters:** `status` (NEW, ACKNOWLEDGED, RESOLVED, FALSE_POSITIVE), `severity` (P0, P1, P2, P3)
- **Response Schema:** List of `AlertResponse`
- **Authentication:** Bearer Token (Admin/Analyst)

### `PATCH /{id}/status`
- **Description:** Updates the status and outcome of an alert.
- **Request Schema:** `AlertUpdateStatusRequest` (status, outcome)
- **Response Schema:** `AlertResponse`
- **Authentication:** Bearer Token (Admin/Analyst)

---
## Synthetic Data Generator (`/api/v1/generator`)

### `POST /start`
- **Description:** Starts the synthetic transaction generator.
- **Authentication:** Bearer Token (Admin)

### `POST /stop`
- **Description:** Stops the synthetic transaction generator.
- **Authentication:** Bearer Token (Admin)

### `GET /status`
- **Description:** Retrieves the current status and metrics of the generator.
- **Response Schema:** `GeneratorStatusResponse` (is_running, current_tps, fraud_rate, queue_depth, active_scenarios)
- **Authentication:** Bearer Token (Admin)

### `PATCH /config`
- **Description:** Updates the generator configuration dynamically.
- **Request Schema:** `GeneratorConfigUpdateRequest` (tps, fraud_injection_rate, active_scenarios)
- **Authentication:** Bearer Token (Admin)

---
## Analytics & Dashboards (`/api/v1/analytics`)

*All analytic endpoints require Bearer Token (Admin/Analyst).*

- **`GET /fraud-rate-trend`**: Returns time-series data for fraud rates.
- **`GET /risk-distribution`**: Returns counts by risk level (LOW, MEDIUM, HIGH, CRITICAL).
- **`GET /geo-fraud`**: Returns geographical fraud concentration data.
- **`GET /device-channel`**: Returns aggregation by device type and channel.
- **`GET /merchant-category`**: Returns fraud grouped by MCC.
- **`GET /time-heatmap`**: Returns a 24x7 matrix of fraud occurrence probabilities.
- **`GET /model-performance`**: Returns ML pipeline metrics (accuracy, precision, recall, f1_score).

---
## Real-Time Streams (`/api/v1/stream`)

### `GET /transactions`
- **Description:** Server-Sent Events (SSE) endpoint emitting real-time transaction scores as they finish the ML pipeline.
- **Response:** `text/event-stream` with JSON payloads.
- **Authentication:** Bearer Token (Admin/Analyst)
