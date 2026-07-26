"""Async collection scheduler.

Design notes (mirrors Thread 13's polling-engine lessons):
- Each probe runs on its own independent loop; a slow or dead target never
  stalls another probe's schedule (no serial loop — the SMF5 lesson).
- Probes return structured Observations and never raise; the runner wraps
  evaluate() defensively anyway so a DB hiccup doesn't kill the loop.
"""
from __future__ import annotations

import asyncio
import logging
import os

import yaml

from middleware.collector.gateway_http import probe_gateway
from middleware.collector.ntp_offset import probe_ntp
from middleware.comparison.engine import evaluate
from middleware.models import SiteBaseline

log = logging.getLogger(__name__)


def load_baseline() -> SiteBaseline:
    path = os.environ.get("MW_BASELINE", "desired-state/sites/lab-a.yaml")
    with open(path) as f:
        raw = yaml.safe_load(f)
    return SiteBaseline.model_validate(raw)  # extra keys / bad types fail here


async def _loop(name: str, interval_s: int, coro_factory, threshold: int) -> None:
    log.info("loop start: %s every %ss", name, interval_s)
    while True:
        try:
            obs = await coro_factory()
            await evaluate(obs, failure_threshold=threshold)
        except Exception:
            log.exception("loop %s: evaluation error (continuing)", name)
        await asyncio.sleep(interval_s)


async def run(baseline: SiteBaseline) -> None:
    gw = baseline.ignition.gateway
    ts = baseline.time_sync
    await asyncio.gather(
        _loop("gateway_http", gw.poll_interval_s,
              lambda: probe_gateway(baseline.site, gw), gw.failure_threshold),
        _loop("ntp_offset", ts.poll_interval_s,
              lambda: probe_ntp(baseline.site, ts), ts.failure_threshold),
    )


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("MW_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    baseline = load_baseline()
    log.info("baseline loaded for site=%s", baseline.site)
    asyncio.run(run(baseline))


if __name__ == "__main__":
    main()
