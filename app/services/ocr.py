import os
import cv2
from pathlib import Path
from fast_alpr import ALPR

_alpr = ALPR(
    detector_model="yolo-v9-t-384-license-plate-end2end",
    ocr_model="cct-xs-v1-global-model",
)


def detect_plate(image_path: str) -> dict:
    """
    Detect license plate from the given image path.
    Saves an annotated output image to the same directory with _output suffix.

    Returns detected_plate, confidence, and output_image_path.

    Raises:
        FileNotFoundError: if the image file does not exist or cannot be read.
        ValueError: if no plate is detected in the image.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found at path: {image_path}")

    frame_bgr = cv2.imread(image_path)
    if frame_bgr is None:
        raise FileNotFoundError(f"Failed to read image at path: {image_path}")

    # fast_alpr expects RGB input
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

    # draw_predictions returns RGB — convert back to BGR for cv2.imwrite
    annotated_rgb = _alpr.draw_predictions(frame_rgb)

    output_path = ""
    if annotated_rgb is not None:
        annotated_bgr = cv2.cvtColor(annotated_rgb, cv2.COLOR_RGB2BGR)
        output_path = _output_path(image_path)
        if not cv2.imwrite(output_path, annotated_bgr):
            output_path = ""

    return {
        "detected_plate": best.ocr.text,
        "confidence": round(best.ocr.confidence, 4),
        "output_image_path": output_path,
    }


def _output_path(image_path: str) -> str:
    p = Path(image_path)
    return str(p.parent / f"{p.stem}_output{p.suffix}")
