# AWS S3 Setup for Fraud Log Archival (Robust / Non-Blocking)

This setup stores **flagged-model logs** in:
1. Local log file (always)
2. AWS S3 objects (best-effort archival)

If S3 is deleted/unavailable, the app keeps working and queues pending uploads locally until S3 is available again.

## 1) Create S3 bucket in AWS Console

1. Open AWS Console -> `S3` -> `Create bucket`.
2. Bucket name: choose globally unique name, e.g. `fraud-platform-logs-<your-suffix>`.
3. Region: use your preferred region (for example `ap-south-1`).
4. Keep defaults unless your org requires specific settings.
5. Create bucket.

## 2) Credentials for programmatic access

Option A (recommended): create dedicated IAM user with only S3 permissions.

Option B (your current choice): create access key under root account security credentials.
Use only for short-term testing and delete the key after tests.

If you choose Option A:
1. Open AWS Console -> `IAM` -> `Users` -> `Create user`.
2. Username: `fraud-log-writer`.
3. Enable `Programmatic access` (Access key).
4. Attach permissions policy (least privilege recommended).

Use this policy (replace bucket name):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::YOUR_BUCKET_NAME",
        "arn:aws:s3:::YOUR_BUCKET_NAME/*"
      ]
    }
  ]
}
```

For either option, copy:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`

## 3) Configure backend environment

Update `backend/.env`:

```env
AWS_S3_ENABLED=true
AWS_REGION=ap-south-1
AWS_S3_BUCKET=YOUR_BUCKET_NAME
AWS_S3_PREFIX=fraud-logs/
AWS_S3_OBJECT_EXTENSION=.txt
AWS_S3_SINGLE_FILE_KEY=fraud logs.txt
AWS_S3_DISABLE_PROXY=true
AWS_S3_SEQUENCE_PATH=
AWS_S3_FLUSH_EVERY_N_RECORDS=25
AWS_S3_RECORDS_PER_OBJECT=200
AWS_S3_MAX_OBJECTS_PER_FLUSH=3
AWS_S3_FLUSH_MIN_INTERVAL_SEC=5
```

Set credentials in your OS environment (recommended), or in `.env` only for local testing:

```env
AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY
AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY
```

## 4) Restart backend

From project root:

```powershell
uvicorn main:app --reload --port 8000
```

## 5) Generate flagged transactions

Run simulation from Generator page with non-trivial fraud rate, or trigger flagged scenarios.

## 6) Verify local + S3 both

### Local file (Wazuh forwarder)

Default path:

`backend/app/wazuh/forwarder/fraud_logs.json`

It should keep growing regardless of S3 availability.

### S3 objects

In bucket, check object key:

`fraud logs.txt`

Notes:
- You do not need to manually create any S3 file.
- The backend creates and updates this text file automatically.
- Each line inside the `.txt` file is one JSON object (JSON Lines format).
- `archive_sequence` inside each record preserves order across large volumes.
- If uploads fail with proxy errors, keep `AWS_S3_DISABLE_PROXY=true`.

## 7) What happens if S3 is deleted?

Expected behavior:

1. Main workflow continues (transactions/alerts/UI unaffected).
2. Local logging continues.
3. S3 uploads fail silently to app flow and are queued in:
   - `backend/runtime/s3_pending_logs.ndjson` (default)
   - sequence state: `backend/runtime/s3_sequence_counter.txt` (default)
4. After you recreate S3 bucket and restore valid credentials, queued logs auto-upload in background.
   - Queue flush is attempted on backend startup and during new flagged log writes.

## 8) Recovery checklist after recreating S3

1. Recreate bucket with same name (or update `AWS_S3_BUCKET` in `.env`).
2. Ensure IAM access key is valid.
3. Restart backend (recommended).
4. Trigger a few new flagged logs.
5. Confirm pending queue shrinks and S3 objects appear.
