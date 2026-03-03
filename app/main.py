from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from app.routes import plate

app = FastAPI(
    title="Parking OCR API",
    description="License plate detection service using ALPR",
    version="1.0.0",
)

app.include_router(plate.router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}
