import os
import cv2
import httpx
import numpy as np
from pathlib import Path
from fast_alpr import ALPR

_alpr = ALPR(
    detector_model="yolo-v9-t-384-license-plate-end2end",
    ocr_model="cct-xs-v1-global-model",
)

_http = httpx.Client(follow_redirects=True, timeout=10.0)


def run_inference(image_path: str) -> dict:
    """
    Load image, run ALPR, draw annotations, encode to JPEG.
    CPU-bound — call via run_in_threadpool.

    Returns dict with detected_plate, confidence, annotated_bytes, and stem
    for async S3 upload by the caller.

    Raises:
        FileNotFoundError: if the image cannot be found or downloaded.
        ValueError: if no plate is detected.
    """
    is_url = image_path.startswith("http://") or image_path.startswith("https://")

    if is_url:
        frame_bgr = _load_from_url(image_path)
    else:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found at path: {image_path}")
        frame_bgr = cv2.imread(image_path)
        if frame_bgr is None:
            raise FileNotFoundError(f"Failed to read image at path: {image_path}")

    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    results = _alpr.predict(frame_rgb)

    if not results:
        raise ValueError("No plate detected in the provided image.")

    best = max(
        (r for r in results if r.ocr),
        key=lambda r: r.ocr.confidence,
        default=None,
    )
    if best is None:
        raise ValueError("No plate detected in the provided image.")

    stem = Path(image_path).stem.split("?")[0]
    annotated_bytes = _encode_annotated(frame_rgb, results)

    return {
        "detected_plate": best.ocr.text,
        "confidence": round(best.ocr.confidence, 4),
        "annotated_bytes": annotated_bytes,
        "stem": stem,
    }


def _encode_annotated(frame_rgb, results) -> bytes:
    """Draw predictions and encode to JPEG bytes. Returns empty bytes on failure."""
    annotated_rgb = _alpr.draw_predictions(frame_rgb)
    if annotated_rgb is None:
        return b""
    annotated_bgr = cv2.cvtColor(annotated_rgb, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", annotated_bgr)
    return buf.tobytes() if ok else b""


def _load_from_url(url: str):
    """Download image from URL into memory and decode with cv2."""
    try:
        resp = _http.get(url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        arr = np.frombuffer(resp.content, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise FileNotFoundError(f"Failed to decode image from URL: {url}")
        return frame
    except httpx.HTTPStatusError as e:
        raise FileNotFoundError(f"HTTP {e.response.status_code} fetching image: {url}")
    except httpx.RequestError as e:
        raise FileNotFoundError(f"Cannot reach URL: {url} — {e}")
