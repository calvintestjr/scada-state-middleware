# ADR-001: MVP Architecture and Project Boundaries

**Status:** Accepted — 2026-07-26
**Deciders:** Calvin (owner), Claude (Senior Infrastructure Architect)

## Context

The middleware (per the July 2026 project brief) compares an approved
desired state against a live Ignition environment, detects drift and
degradation, and generates engineer-approved remediation packages. The
first managed site is the existing Thread 13 lab SCADA stack (Ignition 8.1
+ MySQL 8.0 on MS-01), which is still being wired up in parallel.

## Decisions

### 1. Standalone repository
The middleware lives in its own repo (`scada-state-middleware`), not inside
`enterprise-ai-datacenter/`. It is a product concept with independent
versioning and roadmap. Bootcamp Thread 14 becomes a short integration
document pointing here.

### 2. Dedicated PostgreSQL 16 evidence store
The observer's database is a new Postgres 16 container in this project's
compose stack. It is **not** the SCADA MySQL (an MVP failure scenario is
"database connection disconnected" — the evidence store must not share the
observed database's failure domain) and **not** the host's existing notes
PostgreSQL (standing blast-radius rule).

### 3. Co-located deployment, isolated compose project
Observer runs on the same MS-01 VM as the observed stack, as a separate
Docker Compose project joined to the SCADA stack via one external network.

**Accepted limitation:** host failure takes down observer and observed
together, so a "MS-01 down" event is invisible to the middleware itself.
Acceptable for a lab MVP; production deployment separates the control plane
onto independent infrastructure. Documented deliberately — this is the
honest answer to "what can't your monitor see?"

### 4. API-first walking skeleton (Milestone 1)
No frontend until the pipeline is true end-to-end:
probe → observation (Postgres) → deterministic rule → incident (queryable
via FastAPI). Dashboard is Milestone 3.

### 5. Milestone scoping against Thread 13
Milestone 1 covers the two scenarios independent of Thread 13 completion:
Gateway HTTP reachability and NTP offset. OPC status, DB-connection status,
and tag-quality scenarios (Milestone 2) are **gated on Thread 13** items:
seed-row verification, Ignition `SCADA` DB connection, UDT import, sync
script, Gateway Timer polling.

### 6. Timestamps
All persisted timestamps are UTC (`timestamptz`). `America/New_York` is a
display concern only.

## Consequences

- Two compose projects on MS-01 must use non-conflicting ports and an
  agreed external network name (`scada_observe`).
- The middleware repo carries its own CLAUDE.md, ADRs, and failure-drill
  docs from day one (portfolio-ready standard).
- Milestone 1 gate criterion: stopping the Ignition container produces a
  `critical_outage` incident with linked evidence within 60 seconds.
