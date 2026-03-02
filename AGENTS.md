# AGENTS.md — Python OCR Service

Panduan ini ditujukan untuk AI coding agents (Claude, Copilot, Cursor, dll) yang bekerja di repo ini.
Baca seluruh dokumen sebelum membuat perubahan apapun.

---

## Gambaran Proyek

Service FastAPI kecil yang menerima path file gambar dari Go API via HTTP, menjalankan deteksi plat nomor
menggunakan `fast-alpr`, dan mengembalikan teks plat beserta path gambar hasil anotasi.

Service ini **tidak punya database**, **tidak punya state**, dan **tidak expose endpoint publik** — seluruh
traffic datang dari Go API dalam satu Docker network.

---

## Struktur File

```
Python-OCR/
├── app/
│   ├── main.py              # FastAPI app entry point, health endpoint
│   ├── routes/
│   │   ├── __init__.py
│   │   └── plate.py         # Router: POST /detect-plate
│   └── services/
│       ├── __init__.py
│       └── ocr.py           # Core logic: ALPR model, detect_plate()
├── Dockerfile
├── requirements.txt
├── run.py                   # Uvicorn entry point untuk dev lokal
├── README.md
└── AGENTS.md                # File ini
```

---

## Aturan Wajib

### Image Processing
- `cv2.imread` → output **BGR**
- `fast_alpr.ALPR.predict()` dan `.draw_predictions()` → expect **RGB** input, return **RGB**
- Selalu konversi: `BGR → RGB` sebelum masuk ALPR, `RGB → BGR` sebelum `cv2.imwrite`
- Jangan pernah skip konversi ini — hasilnya akan corrupt secara diam-diam tanpa error

```python
# BENAR
frame_bgr = cv2.imread(path)
frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
results   = _alpr.predict(frame_rgb)
annotated = _alpr.draw_predictions(frame_rgb)
out_bgr   = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)
cv2.imwrite(out_path, out_bgr)

# SALAH — jangan lakukan ini
results   = _alpr.predict(cv2.imread(path))       # BGR masuk ke ALPR
cv2.imwrite(out_path, annotated)                  # RGB ditulis langsung
```

### Output Image Path
- Output image disimpan di direktori yang **sama** dengan input, dengan suffix `_output`
- Contoh: `entry_abc.jpeg` → `entry_abc_output.jpeg`
- Jika `cv2.imwrite` return `False`, set `output_image_path = ""`  — jangan raise exception
- Path yang dikembalikan harus **absolute path di dalam container** (`/mnt/storage/photos/...`)

### Shared Volume
- Go API mount `./storage` ke `/mnt/storage`
- Python OCR juga mount `./storage` ke `/mnt/storage`
- Semua operasi file harus melalui `/mnt/storage/photos/`
- **Jangan hardcode path lain** — selalu gunakan path yang dikirim Go API via `image_path`

### Model ALPR
- Model di-inisialisasi sekali saat modul pertama kali di-import (`_alpr` di level module)
- Jangan inisialisasi ulang ALPR di dalam fungsi request — ini lambat dan boros memori
- Model yang dipakai: detector `yolo-v9-t-384-license-plate-end2end`, OCR `cct-xs-v1-global-model`

### Error Handling di Route
| Exception | HTTP Status |
|---|---|
| `FileNotFoundError` | 404 |
| `ValueError` (no plate detected) | 422 |
| Exception lainnya | 500 |

Jangan ubah mapping ini — Go API bergantung pada status code tersebut untuk menentukan retry vs skip.

---

## Cara Menjalankan Lokal

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
python run.py
# → http://localhost:8000/docs
```

---

## Cara Menjalankan via Docker

```bash
cd ../Go-Api
docker compose up --build python-ocr -d
docker logs parkieee_python_ocr -f
```

**Selalu gunakan `--build`** saat ada perubahan kode — `restart` saja tidak cukup.

---

## Yang Tidak Boleh Diubah Tanpa Koordinasi dengan Go API

- Nama field JSON request/response (`image_path`, `detected_plate`, `confidence`, `output_image_path`)
- HTTP method dan path endpoint (`POST /detect-plate`, `GET /health`)
- HTTP status code untuk setiap jenis error (404/422/500)
- Mount path `/mnt/storage`

Perubahan pada hal-hal di atas akan break Go API secara diam-diam karena Go API tidak ada validasi runtime
terhadap kontrak ini.

---

## Yang Boleh Diubah

- Model ALPR (detector/OCR) — asal update `requirements.txt` jika ada dependency baru
- Logika pemilihan `best` result (saat ini: max confidence)
- Penambahan endpoint baru (tidak menghapus yang lama)
- Konfigurasi Uvicorn di `run.py`

---

## Testing Manual

```bash
# Pastikan ada file gambar di path yang benar, lalu:
curl -X POST http://localhost:8000/detect-plate \
  -H "Content-Type: application/json" \
  -d '{"image_path": "/mnt/storage/photos/entry_xxx.jpeg"}'
```
