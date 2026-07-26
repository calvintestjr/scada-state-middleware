"""Data access layer. asyncpg pool, explicit SQL, no ORM in the MVP —
the schema is small and every query should be readable in review.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import asyncpg

from middleware.models import Classification, Incident, Observation

_pool: asyncpg.Pool | None = None


def _dsn() -> str:
    # Fail loud: no silent defaults for credentials (CLAUDE.md invariant 4).
    try:
        return (
            f"postgresql://{os.environ['MW_DB_USER']}:{os.environ['MW_DB_PASSWORD']}"
            f"@{os.environ['MW_DB_HOST']}:{os.environ.get('MW_DB_PORT', '5432')}"
            f"/{os.environ['MW_DB_NAME']}"
        )
    except KeyError as missing:
        raise RuntimeError(f"Required env var not set: {missing}") from None


async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(_dsn(), min_size=1, max_size=5)
    return _pool


async def insert_observation(obs: Observation) -> int:
    p = await pool()
    return await p.fetchval(
        """INSERT INTO observations (site, probe, target, status, ts, value_num, detail)
           VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb) RETURNING id""",
        obs.site, obs.probe.value, obs.target, obs.status.value, obs.ts,
        obs.value_num, json.dumps(obs.detail),
    )


async def recent_statuses(site: str, probe: str, target: str, n: int) -> list[str]:
    p = await pool()
    rows = await p.fetch(
        """SELECT status FROM observations
           WHERE site=$1 AND probe=$2 AND target=$3
           ORDER BY ts DESC LIMIT $4""",
        site, probe, target, n,
    )
    return [r["status"] for r in rows]


async def open_incident_id(site: str, probe: str, target: str) -> int | None:
    p = await pool()
    return await p.fetchval(
        """SELECT id FROM incidents
           WHERE site=$1 AND probe=$2 AND target=$3 AND state='open'""",
        site, probe, target,
    )


async def create_incident(
    site: str, probe: str, target: str,
    classification: Classification, summary: str, evidence_ids: list[int],
) -> int:
    p = await pool()
    return await p.fetchval(
        """INSERT INTO incidents
             (site, probe, target, classification, opened_at, summary, evidence_ids)
           VALUES ($1,$2,$3,$4,$5,$6,$7)
           ON CONFLICT (site, probe, target) WHERE state='open' DO NOTHING
           RETURNING id""",
        site, probe, target, classification.value,
        datetime.now(timezone.utc), summary, evidence_ids,
    )


async def append_evidence(incident_id: int, obs_id: int) -> None:
    p = await pool()
    await p.execute(
        """UPDATE incidents
           SET evidence_ids = array_append(evidence_ids, $2)
           WHERE id=$1 AND state='open'""",
        incident_id, obs_id,
    )


async def resolve_incident(incident_id: int) -> None:
    p = await pool()
    await p.execute(
        "UPDATE incidents SET state='resolved', resolved_at=$2 WHERE id=$1",
        incident_id, datetime.now(timezone.utc),
    )


async def list_incidents(site: str, state: str | None = None) -> list[dict]:
    p = await pool()
    if state:
        rows = await p.fetch(
            "SELECT * FROM incidents WHERE site=$1 AND state=$2 ORDER BY opened_at DESC",
            site, state)
    else:
        rows = await p.fetch(
            "SELECT * FROM incidents WHERE site=$1 ORDER BY opened_at DESC", site)
    return [dict(r) for r in rows]


async def list_observations(site: str, limit: int = 100) -> list[dict]:
    p = await pool()
    rows = await p.fetch(
        "SELECT * FROM observations WHERE site=$1 ORDER BY ts DESC LIMIT $2",
        site, limit)
    return [dict(r) for r in rows]
