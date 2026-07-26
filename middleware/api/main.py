"""Read-only MVP API. No mutation endpoints exist by design (invariant 3)."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from middleware.db import dal

app = FastAPI(title="scada-state-middleware", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    try:
        p = await dal.pool()
        await p.fetchval("SELECT 1")
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        raise HTTPException(503, detail=f"db unavailable: {type(exc).__name__}")


@app.get("/sites/{site}/observations")
async def observations(site: str, limit: int = 100) -> list[dict]:
    return await dal.list_observations(site, min(limit, 1000))


@app.get("/sites/{site}/incidents")
async def incidents(site: str, state: str | None = None) -> list[dict]:
    if state not in (None, "open", "resolved"):
        raise HTTPException(422, detail="state must be open|resolved")
    return await dal.list_incidents(site, state)
