"""Deterministic comparison engine.

Rules — not AI — decide state (CLAUDE.md invariant 2). The engine consumes
one Observation at a time plus recent history from the evidence store, and
manages the incident lifecycle:

  fail x failure_threshold (consecutive)  -> open incident (debounce)
  degraded                                -> open/maintain 'warning'-tier incident
  error x failure_threshold               -> unknown_state incident
  ok                                      -> resolve any open incident

Duplicate suppression: at most one open incident per (site, probe, target),
enforced by a partial unique index in Postgres — the engine is safe to run
concurrently with itself.
"""
from __future__ import annotations

import logging

from middleware.db import dal
from middleware.models import Classification, Observation, ProbeKind, ProbeStatus

log = logging.getLogger(__name__)

# Classification for a hard-fail condition, per probe (brief §7 taxonomy).
_FAIL_CLASS: dict[ProbeKind, Classification] = {
    ProbeKind.gateway_http: Classification.critical_outage,
    ProbeKind.ntp_offset: Classification.operational_degradation,
}
_DEGRADED_CLASS: dict[ProbeKind, Classification] = {
    ProbeKind.gateway_http: Classification.operational_degradation,
    ProbeKind.ntp_offset: Classification.warning,
}


async def evaluate(obs: Observation, failure_threshold: int) -> None:
    obs_id = await dal.insert_observation(obs)
    existing = await dal.open_incident_id(obs.site, obs.probe.value, obs.target)

    if obs.status == ProbeStatus.ok:
        if existing:
            await dal.append_evidence(existing, obs_id)
            await dal.resolve_incident(existing)
            log.info("resolved incident %s (%s %s)", existing, obs.probe.value, obs.target)
        return

    if existing:
        # Already tracking this condition — accumulate evidence, don't storm.
        await dal.append_evidence(existing, obs_id)
        return

    if obs.status == ProbeStatus.degraded:
        cls = _DEGRADED_CLASS[obs.probe]
        summary = (f"{obs.probe.value} degraded on {obs.target}"
                   f" (value={obs.value_num})")
        await dal.create_incident(obs.site, obs.probe.value, obs.target,
                                  cls, summary, [obs_id])
        log.warning("incident opened: %s", summary)
        return

    # fail / error paths debounce on consecutive history
    recent = await dal.recent_statuses(
        obs.site, obs.probe.value, obs.target, failure_threshold)
    bad = {"fail"} if obs.status == ProbeStatus.fail else {"error"}
    if len(recent) >= failure_threshold and all(s in bad for s in recent):
        if obs.status == ProbeStatus.fail:
            cls = _FAIL_CLASS[obs.probe]
            summary = (f"{obs.probe.value} FAILED on {obs.target}: "
                       f"{failure_threshold} consecutive misses")
        else:
            cls = Classification.unknown_state
            summary = (f"{obs.probe.value} probe erroring on {obs.target}: "
                       f"evidence incomplete, manual investigation required")
        await dal.create_incident(obs.site, obs.probe.value, obs.target,
                                  cls, summary, [obs_id])
        log.error("incident opened: %s", summary)
