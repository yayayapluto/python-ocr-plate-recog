# LPR Service — Python OCR Microservice

FastAPI microservice for license plate recognition. Part of the parkieee stack — accepts a local file path or HTTP(S) URL, runs ALPR, and uploads the annotated image to S3-compatible storage.

---

## Stack

| Component | Technology |
|---|---|
| Framework | FastAPI + Uvicorn |
| Plate detection | [fast-alpr](https://github.com/ankandrew/fast-alpr) (YOLO + CCT ONNX) |
| Image processing | OpenCV |
| HTTP client | httpx |
| Runtime | Python 3.11 |
| Containerization | Docker |

---

## How It Works

```
Go API / Client
  │
  ├─ POST /detect-plate {"image_path": "<local path or URL>"}
  │
  ▼
LPR Service
  ├─ Load image (local path or HTTP(S) URL)
  ├─ Run ALPR: plate detection + OCR
  ├─ Encode annotated image → upload to S3
  └─ Return: detected_plate, confidence, output_image_path (public S3 URL)
```

---

## Endpoints

### `GET /health`

```json
{ "status": "ok" }
```

---

### `POST /detect-plate`

**Request:**
```json
{
  "image_path": "/mnt/storage/photos/entry_d6c2441a.jpeg"
}
```

`image_path` accepts either a local file path **or** a URL (`http://` / `https://`).

**Response 200:**
```json
{
  "detected_plate": "B1701SGI",
  "confidence": 0.9831,
  "output_image_path": "https://<s3-public-base>/entry_d6c2441a_output.jpg"
}
```

`output_image_path` is the public S3 URL of the annotated image. Returns `""` if the upload fails — the plate result is still returned.

**Error responses:**

| Status | Condition |
|---|---|
| `404` | File or URL not found |
| `422` | Valid image but no plate detected |
| `500` | Internal error |

---

## Configuration

Create a `.env` file in the project root (auto-loaded by `run.py`):

```env
S3_ENDPOINT=https://...
S3_BUCKET=bucket-name
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_REGION=us-east-1
S3_PUBLIC_BASE_URL=https://...
```

All six variables are required. The service raises an error at upload time if any are missing.

> S3 uploads use hand-rolled AWS Signature V4 (no boto3) for compatibility with Ceph-based providers such as NevaObjects.

---

## Running Locally

```bash
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt

python run.py
# → http://localhost:8000
# → Interactive docs: http://localhost:8000/docs
```

---

## Running with Docker

```bash
docker build -t lpr-service .
docker run -p 8000:8000 --env-file .env lpr-service
```

---

## ALPR Models

| Parameter | Value |
|---|---|
| Detector | `yolo-v9-t-384-license-plate-end2end` |
| OCR | `cct-xs-v1-global-model` |

Models are downloaded automatically by `fast-alpr` on first run.

`fast-alpr` expects **RGB** input; OpenCV uses **BGR** — the service handles conversion automatically.
