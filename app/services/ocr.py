import os
import tempfile
import urllib.request
import cv2
from pathlib import Path
from fast_alpr import ALPR

from app.services.s3 import upload_to_s3

_alpr = ALPR(
    detector_model="yolo-v9-t-384-license-plate-end2end",
    ocr_model="cct-xs-v1-global-model",
)


def detect_plate(image_path: str) -> dict:
    """
    Detect license plate from the given image path or HTTP(S) URL.
    Always uploads an annotated output image to S3.

    Returns detected_plate, confidence, and output_image_path (public S3 URL).

    Raises:
        FileNotFoundError: if the image cannot be found or downloaded.
        ValueError: if no plate is detected in the image.
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

    output_image_path = _save_annotated_output(image_path, frame_rgb)

    return {
        "detected_plate": best.ocr.text,
        "confidence": round(best.ocr.confidence, 4),
        "output_image_path": output_image_path,
    }


def _save_annotated_output(original_path: str, frame_rgb) -> str:
    """
    Draw predictions on the frame, encode to JPEG, upload to S3.
    Returns the public S3 URL, or empty string if upload fails.
    """
    annotated_rgb = _alpr.draw_predictions(frame_rgb)
    if annotated_rgb is None:
        return ""

    annotated_bgr = cv2.cvtColor(annotated_rgb, cv2.COLOR_RGB2BGR)

    # Derive output filename from original — strip any directory component so
    # the output key is always a flat filename in S3.
    stem = Path(original_path).stem
    # If the original was a URL, stem may contain query params; clean it.
    stem = stem.split("?")[0]
    output_filename = f"{stem}_output.jpg"

    ok, buf = cv2.imencode(".jpg", annotated_bgr)
    if not ok:
        return ""

    try:
        public_url = upload_to_s3(buf.tobytes(), output_filename, "image/jpeg")
        return public_url
    except Exception as exc:
        # Non-fatal — log and return empty so the plate result still comes through.
        print(f"[OCR] warning: failed to upload annotated image to S3: {exc}")
        return ""


def _load_from_url(url: str):
    """Download image from URL into a temp file and read with cv2."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        opener = urllib.request.build_opener()
        opener.addheaders = [("User-Agent", "Mozilla/5.0")]
        with opener.open(url) as response, open(tmp_path, "wb") as f:
            f.write(response.read())

        frame = cv2.imread(tmp_path)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

        if frame is None:
            raise FileNotFoundError(f"Failed to decode image from URL: {url}")
        return frame

    except urllib.error.HTTPError as e:
        raise FileNotFoundError(f"HTTP {e.code} fetching image: {url}")
    except urllib.error.URLError as e:
        raise FileNotFoundError(f"Cannot reach URL: {url} — {e.reason}")
