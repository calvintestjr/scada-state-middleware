"""NTP clock-offset probe (read-only SNTP query).

Compares local clock against the configured NTP server. The probe reports the
measured offset with a status pre-graded against baseline thresholds:
  ok        |offset| <= max_offset_ms
  degraded  |offset| <= critical_offset_ms
  fail      |offset| >  critical_offset_ms
  error     query failed (network, DNS) -> unknown_state upstream
"""
from __future__ import annotations

import asyncio

import ntplib

from middleware.models import Observation, ProbeKind, ProbeStatus, TimeSyncBaseline


def _query(server: str, timeout_s: float) -> float:
    client = ntplib.NTPClient()
    resp = client.request(server, version=3, timeout=timeout_s)
    return resp.offset * 1000.0  # ms; positive = local clock ahead


async def probe_ntp(site: str, cfg: TimeSyncBaseline) -> Observation:
    try:
        offset_ms = await asyncio.to_thread(_query, cfg.ntp_server, cfg.timeout_ms / 1000)
        abs_off = abs(offset_ms)
        if abs_off <= cfg.max_offset_ms:
            status = ProbeStatus.ok
        elif abs_off <= cfg.critical_offset_ms:
            status = ProbeStatus.degraded
        else:
            status = ProbeStatus.fail
        return Observation(
            site=site, probe=ProbeKind.ntp_offset, target=cfg.ntp_server,
            status=status, value_num=round(offset_ms, 3),
            detail={"max_offset_ms": cfg.max_offset_ms,
                    "critical_offset_ms": cfg.critical_offset_ms},
        )
    except Exception as exc:
        return Observation(
            site=site, probe=ProbeKind.ntp_offset, target=cfg.ntp_server,
            status=ProbeStatus.error,
            detail={"error": type(exc).__name__, "msg": str(exc)[:300]},
        )
