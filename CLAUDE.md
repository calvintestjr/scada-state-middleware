# CLAUDE.md — scada-state-middleware

Declarative-state assurance and assisted remediation for SCADA/OT.
Engineer-controlled middleware: detect drift, correlate failures, generate
remediation packages for human approval. **Never an autonomous actor.**

## Non-negotiable invariants

1. **Collectors are read-only.** No code in this repo writes to Ignition, the
   SCADA MySQL database, PLCs, or any observed system. The SCADA MySQL
   container (`mysql` on the SCADA compose network) is OBSERVED-ONLY.
2. **Deterministic rules are authoritative.** Classification, severity,
   thresholds, and compliance come from schemas + rules. AI may summarize
   evidence or draft text; it never decides state or eligibility for action.
3. **No action execution in MVP.** Remediation is generated as a reviewable
   package. There is no code path that executes one.
4. **Fail loud.** Required env vars use `${VAR:?}` in compose. Pydantic
   validates every boundary (desired-state files, observations, API I/O).
   Silent defaults for credentials or hosts are bugs.
5. **Verify, don't recall.** Environment facts (ports, container names, table
   schemas) are confirmed against the running system before being encoded.
   If unverified, mark `# UNVERIFIED` and raise it in review.

## Environment (Site: lab-a)

- Host: MS-01 "Minibeast" VM, Docker Compose. Timezone `America/New_York`;
  all persisted timestamps are UTC.
- Observed stack (separate compose project): Ignition 8.1 Standard trial
  (Vision), MySQL 8.0 backing store, Python polling engine
  (`network_health.py`). Gateway HTTP: `http://<gateway-host>:8088`,
  liveness endpoint `/StatusPing`.
- This stack (observer): PostgreSQL 16 (dedicated container — never reuse
  the SCADA MySQL or the host's notes PostgreSQL), FastAPI app, collector.
- The two compose projects share only an external Docker network for
  collection. Known limitation (ADR-001): shared host = shared failure
  domain; acceptable for lab MVP, documented for production.

## Reference corpus

Ignition behavior questions (gateway config, alarm pipeline, OPC states,
scripting APIs) are answered from the local Ignition 8.1 manual corpus:
`<SCADA project>/manual/*.txt`. Grep the `.txt` files, not the PDFs. Tables
are inline markdown; identifiers are greppable literals. Do not answer
Ignition API questions from memory when the corpus is available.

## Architecture map

- `desired-state/sites/*.yaml` — approved baselines, Git-versioned, validated
  by `middleware/models.py` (Pydantic). Never contain credentials.
- `middleware/collector/` — probes (pure, single-responsibility, bounded
  timeouts) + `runner.py` async scheduler. Per-target debounce lives in the
  comparison layer, not the probe.
- `middleware/comparison/engine.py` — deterministic rules producing
  classifications: informational / approved_deviation / warning /
  configuration_drift / operational_degradation / security_issue /
  critical_outage / unknown_state.
- `middleware/db/` — Postgres schema + data access. Observations are
  append-only evidence; incidents reference observation IDs.
- `middleware/api/` — FastAPI, read-only endpoints in MVP.

## Working agreements

- Every probe has: bounded timeout, structured result (never raises to the
  scheduler), and a unit test.
- Every new rule ships with a controlled failure drill documented in
  `docs/` (how to induce the condition, expected incident output).
- Schema changes to Postgres require an ADR note.
- Milestone 1 gate: stop the Ignition container → `critical_outage` incident
  with evidence within 60 s. Do not add features past the gate until it passes.
