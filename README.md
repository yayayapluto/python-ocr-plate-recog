# README.md — Python OCR Service

Microservice FastAPI untuk deteksi plat nomor kendaraan. Bagian dari stack parkieee, dijalankan sebagai
container terpisah dan berkomunikasi dengan Go API melalui shared Docker volume dan HTTP internal network.

---

## Stack

| Komponen | Teknologi |
|---|---|
| Framework | FastAPI + Uvicorn |
| Deteksi plat | [fast-alpr](https://github.com/ankandrew/fast-alpr) (YOLO + CCT ONNX) |
| Image processing | OpenCV |
| Runtime | Python 3.11 |
| Containerization | Docker |

---

## Cara Kerja

```
Go API
  │
  ├─ 1. Simpan foto ke ./storage/photos/ (shared volume)
  ├─ 2. POST /detect-plate {"image_path": "/mnt/storage/photos/entry_xxx.jpeg"}
  │
  ▼
Python OCR
  ├─ 3. Baca file dari path (shared volume yang sama)
  ├─ 4. Jalankan ALPR: deteksi plat + OCR
  ├─ 5. Simpan gambar anotasi: entry_xxx_output.jpeg
  └─ 6. Return: detected_plate, confidence, output_image_path
```

---

## Struktur Folder

```
Python-OCR/
├── app/
│   ├── main.py              # FastAPI app, health endpoint
│   ├── routes/
│   │   └── plate.py         # POST /detect-plate
│   └── services/
│       └── ocr.py           # ALPR model & detection logic
├── Dockerfile
├── requirements.txt
├── run.py                   # Entry point dev lokal
├── AGENTS.md                # Panduan untuk AI coding agents
└── README.md
```

---

## Endpoints

### `GET /health`
Cek status service. Dipanggil oleh Docker healthcheck dan Go API sebelum dispatch OCR job.

```json
{ "status": "ok" }
```

---

### `POST /detect-plate`

Deteksi plat nomor dari file gambar di shared volume.

**Request:**
```json
{
  "image_path": "/mnt/storage/photos/entry_d6c2441a.jpeg"
}
```

**Response 200:**
```json
{
  "detected_plate": "B1701SGI",
  "confidence": 0.9831,
  "output_image_path": "/mnt/storage/photos/entry_d6c2441a_output.jpeg"
}
```

**Error responses:**

| Status | Kondisi |
|---|---|
| `404` | File tidak ditemukan di path yang diberikan |
| `422` | File valid tapi tidak ada plat terdeteksi |
| `500` | Error internal |

---

## Menjalankan dengan Docker (Rekomendasi)

Service ini dijalankan otomatis lewat `docker-compose.yml` di `Go-Api/`.

```bash
cd Go-Api

# Pertama kali / setelah ada perubahan kode:
docker compose up --build python-ocr -d

# Lihat log:
docker logs parkieee_python_ocr -f
```

> **Catatan:** Gunakan `--build` setiap kali ada perubahan kode Python.
> `docker compose restart` saja **tidak** mengapply perubahan.

---

## Menjalankan Lokal (Development)

```bash
# 1. Buat virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Jalankan server (auto-reload aktif)
python run.py
```

Server berjalan di `http://localhost:8000`.
Dokumentasi interaktif: `http://localhost:8000/docs`

---

## Shared Volume

Go API dan Python OCR berbagi satu bind mount ke folder `./Go-Api/storage/`:

| Container | Mount path di container |
|---|---|
| `parkieee_api` (Go) | `/mnt/storage` |
| `parkieee_python_ocr` (Python) | `/mnt/storage` |

Go API menulis foto ke `/mnt/storage/photos/` → Python baca dari path yang sama →
Python tulis `_output` di path yang sama → Go API bisa serve via `/storage/photos/`.

---

## Model ALPR

| Parameter | Value |
|---|---|
| Detector | `yolo-v9-t-384-license-plate-end2end` |
| OCR | `cct-xs-v1-global-model` |

Model di-download otomatis oleh `fast-alpr` pada saat pertama kali dijalankan.

### Catatan image format
`fast-alpr` menggunakan konvensi **RGB**, sementara OpenCV (`cv2`) menggunakan **BGR**.
Service ini menangani konversi secara otomatis:

```
cv2.imread → BGR → [cvtColor BGR2RGB] → fast-alpr → RGB → [cvtColor RGB2BGR] → cv2.imwrite
```
