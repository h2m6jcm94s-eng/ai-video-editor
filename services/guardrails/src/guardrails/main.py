# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"""FastAPI application for the Guardrails sidecar service."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from guardrails.config import settings
from guardrails.engine import get_engine, GuardrailResult

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─── Pydantic Models ────────────────────────────────────────────────────────


class EvaluateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000, description="Text to evaluate")
    context: str = Field(default="", max_length=1000, description="Optional context (endpoint name)")


class EvaluateResponse(BaseModel):
    allowed: bool
    reason: str | None = None
    flagged_categories: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"
    guardrails_enabled: bool


# ─── FastAPI App ────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: warm up the engine
    logger.info("Guardrails service starting on %s:%d", settings.host, settings.port)
    engine = get_engine()
    logger.info("Engine ready (backend: %s)", "nemo" if engine._nemo and engine._nemo._engine else "heuristic")
    yield
    # Shutdown
    logger.info("Guardrails service shutting down")


app = FastAPI(
    title="AVE Guardrails",
    description="AI safety guardrails sidecar for AI Video Editor",
    version="0.1.0",
    lifespan=lifespan,
)


# ─── Endpoints ──────────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        guardrails_enabled=settings.guardrails_enabled,
    )


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    if not settings.guardrails_enabled:
        return EvaluateResponse(allowed=True)

    engine = get_engine()
    result = engine.evaluate(req.text)

    if not result.allowed:
        logger.warning(
            "Guardrails blocked request: categories=%s, context=%s",
            result.flagged_categories,
            req.context,
        )

    return EvaluateResponse(
        allowed=result.allowed,
        reason=result.reason,
        flagged_categories=result.flagged_categories,
        confidence=result.confidence,
    )


@app.post("/evaluate/batch", response_model=list[EvaluateResponse])
async def evaluate_batch(reqs: list[EvaluateRequest]) -> list[EvaluateResponse]:
    if not settings.guardrails_enabled:
        return [EvaluateResponse(allowed=True) for _ in reqs]

    engine = get_engine()
    results = []
    for req in reqs:
        result = engine.evaluate(req.text)
        results.append(
            EvaluateResponse(
                allowed=result.allowed,
                reason=result.reason,
                flagged_categories=result.flagged_categories,
                confidence=result.confidence,
            )
        )
    return results
