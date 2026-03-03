# AGENTS.md — Python OCR Service

Service FastAPI kecil. Tidak punya database, tidak punya state, tidak expose endpoint publik.
Seluruh traffic datang dari Go API dalam satu Docker network.

---

## Arsitektur

```
Python-OCR/
├── app/
│   ├── main.py              # FastAPI app, health endpoint, load_dotenv()
│   ├── routes/
│   │   └── plate.py         # POST /detect-plate
│   └── services/
│       ├── ocr.py           # ALPR model + detect_plate() — support path & URL input
│       └── s3.py            # upload_to_s3() — AWS Sig V4 native, tanpa SDK
├── Dockerfile
├── requirements.txt
└── run.py                   # Uvicorn entry point
```

---

## Quick Start

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
python run.py
# → http://localhost:8000/docs
```

Via Docker (dari direktori Go-Api):

```bash
docker compose up --build python-ocr -d
docker logs parkieee_python_ocr -f
```

Selalu gunakan `--build` saat ada perubahan kode.

---

## Environment Variables

Diload via `python-dotenv` saat startup (`main.py` paling atas).

| Variable            | Wajib | Default      | Keterangan                                     |
|---------------------|-------|--------------|------------------------------------------------|
| `S3_ENDPOINT`       | ✅    | —            | e.g. `https://s3.nevaobjects.id`               |
| `S3_BUCKET`         | ✅    | —            | nama bucket                                    |
| `S3_ACCESS_KEY`     | ✅    | —            | access key                                     |
| `S3_SECRET_KEY`     | ✅    | —            | secret key                                     |
| `S3_PUBLIC_BASE_URL`| ✅    | —            | e.g. `https://parkieee.s3.nevaobjects.id`      |
| `S3_REGION`         | ❌    | `us-east-1`  | region bucket                                  |

Kalau S3 env tidak lengkap, `upload_to_s3()` raise `RuntimeError` — output image tidak tersimpan
tapi deteksi plate tetap berhasil (non-fatal, return `output_image_path: ""`).

---

## HTTP Contract (JANGAN UBAH tanpa koordinasi Go API)

```
POST /detect-plate
Content-Type: application/json
{ "image_path": "https://parkieee.s3.nevaobjects.id/entry_xxx.jpeg" }

200 → { "detected_plate": "B1701SGI", "confidence": 0.9831, "output_image_path": "https://...entry_xxx_output.jpg" }
404 → { "detail": "Cannot find image" }
422 → { "detail": "No plate detected in the provided image" }
500 → { "detail": "Internal server error: ..." }

GET /health
200 → { "status": "ok" }
```

`image_path` sekarang adalah **public S3 URL** (bukan path volume).
Go API bergantung pada status code ini untuk retry vs skip — jangan ubah mapping-nya.

Output `output_image_path` adalah **public S3 URL** dari annotated image.
Go API ambil URL ini langsung untuk disimpan ke `ocr_results.output_image_url`.

---

## Status Implementasi

| File                    | Status |
|-------------------------|--------|
| `app/main.py`           | ✅ done |
| `app/routes/plate.py`   | ✅ done |
| `app/services/ocr.py`   | ✅ done — support URL + path input, upload output ke S3 |
| `app/services/s3.py`    | ✅ done — AWS Sig V4 native, tanpa boto3/SDK            |
| `requirements.txt`      | ✅ done — ditambah python-dotenv                        |
| `Dockerfile`            | ✅ done — hapus volume mkdir, lebih slim                |

Tidak ada modul yang planned — service ini sudah feature-complete untuk scope MVP.

---

## What's Done / What's Not

| Area                        | Status                                                              |
|-----------------------------|---------------------------------------------------------------------|
| `POST /detect-plate`        | ✅ done — ALPR detect + annotate + upload output ke S3              |
| `GET /health`               | ✅ done — ping dari Go API sebelum tiap job                         |
| ALPR model init             | ✅ done — singleton di level module, tidak re-init per req           |
| BGR↔RGB conversion          | ✅ done — lihat agents-logic.md untuk aturan wajibnya               |
| URL image input             | ✅ done — `image_path` bisa HTTP(S) URL atau local path             |
| S3 output upload            | ✅ done — annotated image di-upload ke S3, return public URL        |
| AWS Sig V4 native           | ✅ done — tanpa boto3, kompatibel dengan NevaObjects (Ceph)         |
| Multi-plate best-pick       | ✅ done — max confidence dari semua result                          |
| Error handling 404/422/500  | ✅ done — Go API pakai ini untuk retry vs skip logic                |
| python-dotenv               | ✅ done — env vars diload dari .env saat startup                    |
