from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.ocr import detect_plate

router = APIRouter(prefix="/detect-plate", tags=["Plate Detection"])


class DetectPlateRequest(BaseModel):
    image_path: str


class DetectPlateResponse(BaseModel):
    detected_plate: str
    confidence: float
    output_image_path: Optional[str] = None


@router.post(
    "",
    response_model=DetectPlateResponse,
    summary="Detect license plate from image",
    description="Accepts an image path from shared Docker volume and returns the detected plate number, confidence score, and path to the annotated output image.",
)
def detect_plate_endpoint(body: DetectPlateRequest):
    try:
        result = detect_plate(body.image_path)
        return DetectPlateResponse(**result)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Cannot find image")

    except ValueError:
        raise HTTPException(status_code=422, detail="No plate detected in the provided image")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
