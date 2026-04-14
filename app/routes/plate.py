import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional
from app.services.ocr import run_inference
from app.services.s3 import upload_to_s3_async

router = APIRouter(prefix="/detect-plate", tags=["Plate Detection"])
logger = logging.getLogger(__name__)


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


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
    description="Accepts an image path or HTTP(S) URL. Returns the detected plate number, confidence score, and path to the annotated output image.",
)
async def detect_plate_endpoint(
    body: DetectPlateRequest,
    client: httpx.AsyncClient = Depends(get_http_client),
):
    try:
        result = await run_in_threadpool(run_inference, body.image_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Cannot find image")
    except ValueError:
        raise HTTPException(status_code=422, detail="No plate detected in the provided image")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    output_image_path = ""
    if result.get("annotated_bytes"):
        try:
            output_image_path = await upload_to_s3_async(
                result["annotated_bytes"],
                f"{result['stem']}_output.jpg",
                client,
            )
        except Exception as e:
            logger.warning("Failed to upload annotated image to S3: %s", e)

    return DetectPlateResponse(
        detected_plate=result["detected_plate"],
        confidence=result["confidence"],
        output_image_path=output_image_path,
    )
