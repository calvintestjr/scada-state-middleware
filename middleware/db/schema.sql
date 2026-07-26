-- Evidence store schema (ADR-001 decision 2). All timestamps UTC.
-- Observations are append-only evidence. Incidents reference them.

CREATE TABLE IF NOT EXISTS observations (
    id          BIGSERIAL PRIMARY KEY,
    site        TEXT        NOT NULL,
    probe       TEXT        NOT NULL,
    target      TEXT        NOT NULL,
    status      TEXT        NOT NULL,          -- ok | degraded | fail | error
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    value_num   DOUBLE PRECISION,
    detail      JSONB       NOT NULL DEFAULT '{}'::jsonb
);

-- Debounce + evidence queries: "last N for this target, newest first".
CREATE INDEX IF NOT EXISTS ix_obs_target_ts
    ON observations (site, probe, target, ts DESC);

CREATE TABLE IF NOT EXISTS incidents (
    id              BIGSERIAL PRIMARY KEY,
    site            TEXT        NOT NULL,
    probe           TEXT        NOT NULL,
    target          TEXT        NOT NULL,
    classification  TEXT        NOT NULL,
    state           TEXT        NOT NULL DEFAULT 'open',   -- open | resolved
    opened_at       TIMESTAMPTZ NOT NULL,
    resolved_at     TIMESTAMPTZ,
    summary         TEXT        NOT NULL,
    evidence_ids    BIGINT[]    NOT NULL DEFAULT '{}'
);

-- One open incident per (site, probe, target): the engine updates evidence on
-- an existing open incident instead of storming duplicates (brief §8 lesson —
-- Thread 13 flagged alarm-journal bloat from flapping devices; same principle).
CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_open
    ON incidents (site, probe, target)
    WHERE state = 'open';

CREATE INDEX IF NOT EXISTS ix_incidents_site_state
    ON incidents (site, state, opened_at DESC);
