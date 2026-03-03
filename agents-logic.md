# agents-logic.md — Python OCR Service Logic Reference

Baca sebelum mengubah apapun di service ini.

---

## Flow Utama: detect_plate()

```
Input: image_path (str) — public S3 URL atau path absolut lokal

1. Cek apakah image_path adalah URL (startswith "http://" / "https://")
   └─ URL → _load_from_url(url) → frame_bgr
   └─ Path → os.path.exists(image_path)
              └─ False → raise FileNotFoundError
              cv2.imread(image_path) → frame_bgr
              └─ None → raise FileNotFoundError

2. cv2.cvtColor(BGR → RGB) → frame_rgb
   ← fast_alpr SELALU expect RGB input

3. _alpr.predict(frame_rgb) → results[]
   └─ [] kosong → raise ValueError

4. best = max(results, key=r.ocr.confidence)
   └─ Semua result tidak punya OCR text → raise ValueError

5. _save_annotated_output(original_path, frame_rgb)
   → draw_predictions → encode JPEG → upload_to_s3() → public URL
   └─ Gagal upload (non-fatal) → return ""

6. return {
       detected_plate: best.ocr.text,
       confidence: round(best.ocr.confidence, 4),
       output_image_path: public_url_or_empty,
   }
```

---

## _load_from_url()

```
Input: url (str) — public S3 URL

1. Download ke tempfile menggunakan urllib.request dengan custom User-Agent
2. cv2.imread(tmp_path) → frame_bgr
3. Hapus tempfile (os.unlink, non-fatal kalau gagal)
4. Return frame_bgr

Raises:
  FileNotFoundError ← urllib.error.HTTPError (misal 403, 404)
  FileNotFoundError ← urllib.error.URLError (unreachable)
  FileNotFoundError ← cv2.imread return None
```

Tidak pakai `requests` — sengaja pakai `urllib` standar library untuk menghindari
dependency tambahan. Cukup untuk download dari S3 public URL.

---

## _save_annotated_output()

```
Input: original_path (str), frame_rgb (ndarray)

1. _alpr.draw_predictions(frame_rgb) → annotated_rgb
   └─ None → return ""

2. cv2.cvtColor(RGB → BGR) → annotated_bgr

3. Derive output filename:
   stem = Path(original_path).stem
   stem = stem.split("?")[0]   ← strip query params kalau URL
   output_filename = f"{stem}_output.jpg"

4. cv2.imencode(".jpg", annotated_bgr) → buf
   └─ False → return ""

5. upload_to_s3(buf.tobytes(), output_filename, "image/jpeg")
   └─ Exception → log warning + return "" (non-fatal)

6. Return public S3 URL
```

Output image selalu `.jpg` — terlepas dari ekstensi input.
Filename derivation dari stem path/URL supaya konsisten dengan Go API convention.

---

## BGR ↔ RGB — Aturan Wajib

`cv2.imread` selalu return **BGR**. `fast_alpr` selalu expect dan return **RGB**.
Konversi ini non-negotiable — skip akan menghasilkan deteksi salah secara diam-diam.

```python
# BENAR
frame_bgr = cv2.imread(path)           # atau _load_from_url()
frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
results   = _alpr.predict(frame_rgb)
annotated = _alpr.draw_predictions(frame_rgb)   # juga return RGB
out_bgr   = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)
cv2.imwrite(out_path, out_bgr)         # atau imencode + upload S3

# SALAH
results = _alpr.predict(cv2.imread(path))       # BGR masuk ALPR
cv2.imwrite(out_path, annotated)               # RGB ditulis sebagai BGR
```

---

## S3 Upload: upload_to_s3()

```
Input: data (bytes), filename (str), content_type (str)

1. Baca env: S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY,
             S3_REGION (default "us-east-1"), S3_PUBLIC_BASE_URL
   └─ Ada yang kosong → raise RuntimeError

2. Build AWS Signature V4:
   - canonical headers: content-type, host, x-amz-content-sha256, x-amz-date (sorted)
   - credential scope: {date}/{region}/s3/aws4_request
   - string to sign: AWS4-HMAC-SHA256 + amz_date + cred_scope + sha256(canonical_request)
   - signing key: HMAC chain (secret → date → region → service → aws4_request)
   - signature: HMAC-SHA256(signing_key, string_to_sign) hex

3. PUT {endpoint}/{bucket}/{filename}
   Headers: Content-Type, x-amz-date, x-amz-content-sha256, Authorization, Content-Length

4. Status 200 atau 201 → OK
   HTTPError → raise RuntimeError dengan body response
   Status lain → raise RuntimeError

5. Return f"{S3_PUBLIC_BASE_URL}/{filename}"
```

Implementasi ini mirror exact Go API (`pkg/photo/photo.go`) — sama-sama tidak pakai SDK
supaya kompatibel dengan NevaObjects (Ceph-based) yang reject beberapa SDK-generated headers.

---

## Output URL Convention

```
input image_path : https://parkieee.s3.nevaobjects.id/entry_abc123_1772000000.jpeg
output           : https://parkieee.s3.nevaobjects.id/entry_abc123_1772000000_output.jpg
```

Stem diambil dari Path(url).stem → `entry_abc123_1772000000` → tambah `_output.jpg`.
Go API menyimpan URL ini langsung ke `ocr_results.output_image_url`.

---

## Model ALPR

```python
_alpr = ALPR(
    detector_model="yolo-v9-t-384-license-plate-end2end",
    ocr_model="cct-xs-v1-global-model",
)
```

Di-inisialisasi **sekali saat modul di-import** — singleton di level module.
Jangan pindahkan ke dalam fungsi request — cold start ALPR lambat dan boros memori.

---

## Error → HTTP Status Mapping

| Exception           | HTTP | Trigger Go API |
|---------------------|------|----------------|
| `FileNotFoundError` | 404  | skip job       |
| `ValueError`        | 422  | skip job       |
| Exception lainnya   | 500  | retry          |

Go API membedakan 404/422 (skip) vs 500 (retry hingga maxRetries). Jangan ubah mapping ini.

---

## Dependencies

```
fastapi        — HTTP framework
uvicorn        — ASGI server
opencv-python  — cv2.imread, cvtColor, imencode, imwrite
onnxruntime    — runtime untuk model ALPR (dipakai internal fast-alpr)
fast-alpr      — wrapper ALPR: YOLO detector + CCT OCR model
python-dotenv  — load .env saat startup (main.py: load_dotenv() sebelum import app)
```

Tidak ada `boto3` atau AWS SDK — S3 diakses via raw HTTP + AWS Sig V4 di `services/s3.py`.
Tidak ada `requests` — download URL pakai `urllib.request` (stdlib).

---

## Startup Order (main.py)

```python
from dotenv import load_dotenv
load_dotenv()                  # HARUS pertama sebelum import apapun yang butuh env

from fastapi import FastAPI
from app.routes import plate   # import ini trigger _alpr singleton init
```

`load_dotenv()` harus dipanggil **sebelum** import `plate` (yang import `ocr` yang import `s3`).
Kalau urutan dibalik, `os.environ.get()` di `s3.py` akan dapat empty string.
