from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI
from app.routes import plate


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()
    yield
    await app.state.http_client.aclose()


app = FastAPI(
    title="Parking OCR API",
    description="License plate detection service using ALPR",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(plate.router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}
