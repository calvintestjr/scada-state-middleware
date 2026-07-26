# scada-state-middleware

Engineer-controlled declarative-state assurance for SCADA/OT.
Compares an approved, Git-versioned baseline against a live Ignition
environment; detects drift and degradation; opens deduplicated, evidenced
incidents; (later) generates human-approved remediation packages.

**Read-only by design.** No code path writes to any observed system.

## Milestone 1 — walking skeleton (current)
probe → observation (Postgres) → deterministic rule → incident → FastAPI.
Scenarios: Ignition Gateway reachability, NTP clock offset.

## Quick start (MS-01)
```bash
docker network create scada_observe          # once; attach Ignition stack too
cp .env.example .env                         # fill MW_DB_PASSWORD
docker compose up -d --build
curl localhost:8090/health
curl localhost:8090/sites/lab-a/incidents?state=open
```

## Milestone 1 gate drill
```bash
docker stop <ignition-container>
# within ~60s (10s poll x 3-miss debounce + margin):
curl localhost:8090/sites/lab-a/incidents?state=open
# expect one critical_outage incident with evidence_ids populated
docker start <ignition-container>
# incident auto-resolves on next ok observation
```

## Docs
- `CLAUDE.md` — invariants and working agreements (read first)
- `docs/adr/ADR-001` — MVP architecture decisions
