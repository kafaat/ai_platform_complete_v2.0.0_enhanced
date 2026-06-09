"""SAHOOL v9.1.0 — services/agriai-engine/main.py
Agricultural AI Engine — crop recommendations and yield optimization.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","svc":"agriai","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger("agriai-engine")

VERSION = "9.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("✅ agriai-engine started")
    yield
    logger.info("agriai-engine stopped")


app = FastAPI(title="SAHOOL AgriAI Engine", version=VERSION, lifespan=lifespan)


@app.get("/healthz")
@app.get("/health")
async def health():
    return {"status": "alive", "service": "agriai-engine", "version": VERSION}


@app.get("/readyz")
async def readyz():
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


class RecommendRequest(BaseModel):
    """نموذج تحقّق لطلب التوصية — يرفض القيم خارج النطاق."""

    field_id: str = ""
    crop: str = "wheat"
    ndvi: float = Field(0.5, ge=-1.0, le=1.0)
    soil_ph: float = Field(7.0, ge=0, le=14)


AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")


def _require_service_token(x_agent_token: str = Header(None)) -> None:
    if not AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — معطّل بأمان")
    if x_agent_token != AGENT_TOKEN:
        raise HTTPException(401, "توكن خدمة غير صالح")


@app.post("/recommend")
async def recommend(req: RecommendRequest, x_agent_token: str = Header(None)):
    _require_service_token(x_agent_token)
    """Generate AI-powered crop recommendations."""
    field_id = req.field_id
    crop = req.crop
    ndvi = req.ndvi
    # Stub — implement with ML model
    return {
        "field_id": field_id,
        "crop": crop,
        "recommendations": [
            {"action": "irrigation", "priority": "high" if ndvi < 0.4 else "medium"},
            {"action": "fertilization", "priority": "medium"},
        ],
        "confidence": 0.82,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
