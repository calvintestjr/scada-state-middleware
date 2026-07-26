"""Boundary models. Everything entering the system validates here.

Design rules (ADR-001, CLAUDE.md):
- extra="forbid" on baseline models: a typo'd key in a desired-state file is
  a hard failure at load time, not a silently ignored setting.
- Observations are structured results, never exceptions: probes cannot crash
  the scheduler.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


# ---------------------------------------------------------------- desired state

class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GatewayBaseline(_Strict):
    base_url: str
    liveness_path: str = "/StatusPing"
    expected_state: str = "running"
    poll_interval_s: int = Field(10, ge=1)
    timeout_ms: int = Field(3000, ge=100)
    failure_threshold: int = Field(3, ge=1)


class OpcConnectionBaseline(_Strict):
    enabled: bool = True
    expected_status: str = "connected"


class DbConnectionBaseline(_Strict):
    enabled: bool = True
    expected_status: str = "connected"
    host: str
    port: int = Field(ge=1, le=65535)


class TagQualityBaseline(_Strict):
    enabled: bool = True
    max_bad_quality_pct: float = Field(5.0, ge=0, le=100)


class IgnitionBaseline(_Strict):
    gateway: GatewayBaseline
    opc_connections: dict[str, OpcConnectionBaseline] = {}
    database_connections: dict[str, DbConnectionBaseline] = {}
    tag_quality: TagQualityBaseline | None = None


class TimeSyncBaseline(_Strict):
    ntp_server: str
    max_offset_ms: float = Field(250, gt=0)
    critical_offset_ms: float = Field(2000, gt=0)
    poll_interval_s: int = Field(60, ge=5)
    timeout_ms: int = Field(3000, ge=100)
    failure_threshold: int = Field(3, ge=1)


class SiteBaseline(_Strict):
    site: str
    timezone_display: str = "UTC"
    ignition: IgnitionBaseline
    time_sync: TimeSyncBaseline


# ---------------------------------------------------------------- observations

class ProbeKind(str, Enum):
    gateway_http = "gateway_http"
    ntp_offset = "ntp_offset"
    # Milestone 2:
    opc_status = "opc_status"
    db_connection = "db_connection"
    tag_quality = "tag_quality"


class ProbeStatus(str, Enum):
    ok = "ok"
    degraded = "degraded"
    fail = "fail"
    error = "error"   # probe itself malfunctioned -> maps to unknown_state


class Observation(BaseModel):
    site: str
    probe: ProbeKind
    target: str
    status: ProbeStatus
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    value_num: float | None = None       # e.g. rtt ms, offset ms
    detail: dict[str, Any] = {}


# ------------------------------------------------------------------- incidents

class Classification(str, Enum):
    informational = "informational"
    approved_deviation = "approved_deviation"
    warning = "warning"
    configuration_drift = "configuration_drift"
    operational_degradation = "operational_degradation"
    security_issue = "security_issue"
    critical_outage = "critical_outage"
    unknown_state = "unknown_state"


class IncidentState(str, Enum):
    open = "open"
    resolved = "resolved"


class Incident(BaseModel):
    id: int | None = None
    site: str
    probe: ProbeKind
    target: str
    classification: Classification
    state: IncidentState = IncidentState.open
    opened_at: datetime
    resolved_at: datetime | None = None
    summary: str
    evidence_ids: list[int] = []
