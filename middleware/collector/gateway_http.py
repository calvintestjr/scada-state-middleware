"""Ignition Gateway liveness probe (read-only HTTP GET).

Ignition 8.1 exposes /StatusPing on the Gateway web port; a healthy Gateway
answers with body containing RUNNING. (Verify against the live Gateway per
CLAUDE.md invariant 5 — trial editions and reverse proxies can differ.)
Probe returns a structured Observation and never raises.
"""
from __future__ import annotations

import time

import httpx

from middleware.models import GatewayBaseline, Observation, ProbeKind, ProbeStatus


async def probe_gateway(site: str, cfg: GatewayBaseline) -> Observation:
    url = cfg.base_url.rstrip("/") + cfg.liveness_path
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=cfg.timeout_ms / 1000) as client:
            resp = await client.get(url)
        rtt_ms = (time.monotonic() - t0) * 1000
        body = resp.text[:200]
        if resp.status_code == 200 and "RUNNING" in body.upper():
            status = ProbeStatus.ok
        elif resp.status_code == 200:
            # Reachable but not reporting RUNNING (e.g. commissioning, faulted)
            status = ProbeStatus.degraded
        else:
            status = ProbeStatus.fail
        return Observation(
            site=site, probe=ProbeKind.gateway_http, target=cfg.base_url,
            status=status, value_num=round(rtt_ms, 2),
            detail={"http_status": resp.status_code, "body_head": body.strip()},
        )
    except httpx.TimeoutException:
        return Observation(
            site=site, probe=ProbeKind.gateway_http, target=cfg.base_url,
            status=ProbeStatus.fail,
            detail={"error": "timeout", "timeout_ms": cfg.timeout_ms},
        )
    except Exception as exc:  # probe malfunction != target down
        return Observation(
            site=site, probe=ProbeKind.gateway_http, target=cfg.base_url,
            status=ProbeStatus.error,
            detail={"error": type(exc).__name__, "msg": str(exc)[:300]},
        )
