# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server (loads .env automatically)
python run.py

# Run without auto-reload (production-like)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Build and run with Docker
docker build -t lpr-service .
docker run -p 8000:8000 --env-file .env lpr-service
```

## Architecture

Single-responsibility FastAPI service that accepts an image (local path or HTTP(S) URL), runs ALPR, and returns the detected plate text, confidence, and a public S3 URL of the annotated image.

**Request flow:**
1. `POST /detect-plate` → `app/routes/plate.py` — runs CPU-bound inference in a threadpool, then `await`s the async S3 upload separately so inference never blocks on network I/O.
2. `app/services/ocr.py` — module-level `ALPR` singleton and `httpx.Client` (with 10 s timeout). `run_inference()` loads the image (local path or URL), runs ALPR, draws annotations, returns plate info + raw JPEG bytes. Does not touch S3.
3. `app/services/s3.py` — `upload_to_s3_async()` uploads annotated JPEG bytes using hand-rolled AWS Signature V4 (no boto3). This is intentional: Ceph-based providers (e.g. NevaObjects) reject extra headers added by the AWS SDK. Retries once on transient failure.

**ALPR models** (loaded in `ocr.py`):
- Detector: `yolo-v9-t-384-license-plate-end2end`
- OCR: `cct-xs-v1-global-model`

## Environment Variables

Create a `.env` file (loaded by `run.py` via `python-dotenv`):

```
S3_ENDPOINT=https://...
S3_BUCKET=...
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_REGION=us-east-1
S3_PUBLIC_BASE_URL=https://...
```

All six variables are required; the service raises `RuntimeError` at upload time if any are missing.

## Key Design Decisions

- The `ALPR` instance and `httpx.Client` are **module-level singletons** in `ocr.py`. Do not move them inside functions.
- S3 signing is done manually without boto3 to avoid Ceph header-rejection issues. Keep it that way unless the provider changes.
- `image_path` in the request body doubles as both a filesystem path and an HTTP(S) URL — check `is_url` logic in `ocr.py:run_inference` before adding new input handling.
- S3 upload runs **after** the threadpool returns, directly in the async event loop (`upload_to_s3_async`). Keep inference and upload decoupled this way.
