# Drill Record: M1-NTP — Unplanned Detection of Host Clock Desynchronization

**Date:** 2026-07-26 / 2026-07-27 UTC
**Site:** lab-a
**Probe:** `ntp_offset`
**Type:** **Unplanned** — real fault detected on the collector's first run.
Not a staged failure injection.
**Outcome:** Root cause identified and remediated. Three incidents raised,
three auto-resolved. False positives: 0.
**Related:** ADR-002

---

## 1. Summary

The `ntp_offset` probe opened an incident 153 ms into its first execution.
Initial assumption was a false positive from an over-tight threshold. It was
not. The Windows Docker host's `w32time` service was Stopped with StartType
Manual, leaving the system clock undisciplined and free-running. Measured
offset grew from 660 ms to 2.4 s over roughly six minutes.

Two hypotheses were formed and both were disproved by measurement before the
actual root cause was found. The threshold was never changed.

---

## 2. Detection

First collector run, 2026-07-26 23:40:14 UTC:

```
INFO  __main__ baseline loaded for site=lab-a
INFO  __main__ loop start: gateway_http every 10s
INFO  __main__ loop start: ntp_offset every 60s
WARN  middleware.comparison.engine incident opened:
      ntp_offset degraded on pool.ntp.org (value=660.125)
```

Classification `warning` (offset above `max_offset_ms: 250`, below
`critical_offset_ms: 2000`). Correct per policy.

---

## 3. Hypothesis 1 — WSL2 clock drift (DISPROVED)

**Reasoning:** host is Windows Docker Desktop on the WSL2 backend. The WSL2 VM
maintains its own clock, which is known to drift from the Windows host,
especially after host sleep/hibernate. Expected finding: container clock wrong,
host clock correct.

**Test:** sample container offset five times; compare against the host's own
measurement.

```
# container (docker exec mw-collector, ntplib -> pool.ntp.org, ms)
2402.5  2410.6  2420.6  2430.6  2439.2

# Windows host (w32tm /stripchart /computer:pool.ntp.org)
19:46:01, +02.5245290s
19:46:03, +02.5255350s
19:46:05, +02.5262264s
```

**Disproved.** Host and container agree to within milliseconds — both ~2.4 s
off. The container was faithfully inheriting a wrong *host* clock. The fault
was upstream of WSL2 entirely.

**Second finding from the same data:** the offset climbs monotonically,
~37 ms across five samples taken seconds apart. Measurement noise scatters;
this marched. Normal quartz drift is milliseconds per hour, not per second.
That signature means nothing was correcting the clock — pointing directly at
the time service.

---

## 4. Hypothesis 2 — SNTP path asymmetry (DISPROVED as primary cause)

**Reasoning:** offset measured through container → Docker NAT → WSL2 vNIC →
Windows stack → internet. `ntplib` assumes a symmetric round trip; asymmetry
inflates apparent offset. Expected finding: measurement artifact, clock fine.

**Test:** query the host time service state directly.

```
w32tm /query /status
w32tm /query /source
Get-Service w32time
```

```
The following error occurred: The service has not been started. (0x80070426)
w32time   Stopped   Manual
```

**Disproved as primary cause.** The service was not running. Path asymmetry
could not account for a 2.4 s error, and there was a much simpler explanation
sitting in front of it. (Asymmetry *does* turn out to explain the ~160 ms
residual after remediation — see §7.)

---

## 5. Root cause

**`w32time` service Stopped, StartType Manual.** No time source was being
polled; the system clock was free-running on quartz oscillator drift, and the
error accumulated without bound.

Dependency chain, symptom to cause:

```
alarm/historian timestamp risk
  <- container clock offset (probe-visible symptom)
    <- Windows host clock offset
      <- w32time service not running
        <- StartType Manual + service stopped (root cause)
```

The probe observed the effect three layers below the cause. This is the
dependency-aware correlation the project brief describes (§8) occurring
naturally rather than by design — worth noting as validation of the model.

---

## 6. Remediation — and the recovery/remediation distinction

First attempt (partial, and instructive):

```powershell
Set-Service w32time -StartupType Automatic
Start-Service w32time
w32tm /resync /force
```

Result:

```
Leap Indicator: 3(not synchronized)
Stratum: 0 (unspecified)
ReferenceId: 0x00000000 (unspecified)
Root Dispersion: 10.3312116s
Last Successful Sync Time: 7/26/2026 7:55:00 PM
Source: time.windows.com,0x9
```

Service **running but not synchronized** — no trusted upstream reference.
`time.windows.com` was not answering usefully. Single-peer configuration =
single point of failure.

Second attempt (successful):

```powershell
w32tm /config /manualpeerlist:"time.windows.com,0x9 time.nist.gov,0x9 pool.ntp.org,0x9" /syncfromflags:manual /update
Restart-Service w32time
w32tm /resync /force
```

Result:

```
Leap Indicator: 0(no warning)
Stratum: 2 (secondary reference - syncd by (S)NTP)
ReferenceId: 0x84A36001 (source IP:  132.163.96.1)   # NIST
Source: time.nist.gov,0x9
```

The multi-peer list was not redundancy for its own sake — it was the fix.
NIST answered where Microsoft's pool did not.

**Recovery vs. remediation.** `Start-Service` restored function for the
current boot only. `Set-Service -StartupType Automatic` is the durable fix.
Conflating the two produces an incident that silently returns after the next
reboot. Remediation packages generated by this platform must distinguish the
two explicitly.

---

## 7. Verification — three-stage measurement progression

| Host state | Container offset (ms) | Signature |
|---|---|---|
| `w32time` Stopped | 2402 → 2439, climbing | Monotonic growth; unbounded |
| Running, unsynchronized (LI=3, Stratum 0) | ~263–268 | Stable, ~4 ms spread |
| Synchronized (LI=0, Stratum 2, NIST) | **158–166** | Stable, ~8 ms spread |

Final state: 158–166 ms, **under** the unchanged 250 ms threshold with ~85 ms
headroom. The residual is attributed to SNTP path asymmetry through the Docker
Desktop NAT (Hypothesis 2, correct as a secondary effect).

Incident lifecycle, from the API:

| ID | Opened | Resolved | Duration | Peak offset | Evidence rows |
|---|---|---|---|---|---|
| 1 | 23:40:14 | 23:55:49 | 15m 35s | 660 ms | 15 |
| 2 | 23:58:56 | 00:07:11 | 8m 15s | 320 ms | 9 |
| 3 | 00:10:20 | 00:11:21 | **61s** | 273 ms | 2 |

All three auto-resolved on the first `ok` observation. Final state: zero open
incidents.

Incident 3 is the most informative: a 61-second transient captured while
`w32time` was still converging after resync, opened and closed cleanly within
one poll cycle. The engine was exercised against fault durations of 15
minutes, 8 minutes, and 1 minute — including correct closure in all three.

---

## 8. Findings that change the product

**(a) "Last successful sync" is not a health signal.**
The unsynchronized state reported `Last Successful Sync Time: 7:55:00 PM` —
recent, plausible, and completely misleading. A monitor checking only that
field would have reported healthy while the clock was 2.4 s wrong and
diverging. The authoritative fields are **Leap Indicator** (0 = synchronized)
and **Stratum** (0 = no reference), corroborated by **Root Dispersion** as the
service's own error bound.

Generalization: *a timestamp of last success measures whether something ever
worked, not whether it is working.* This applies directly to the other MVP
scenarios — backup freshness, certificate checks, historian store-and-forward.
Any check whose evidence is "last time X succeeded" needs a companion check on
current reference validity.

**(b) The threshold was never the problem.**
Raising `max_offset_ms` on first fire — the tempting response to a noisy new
check — would have masked a genuine 2.4-second fault, prevented discovery of
the disabled service, and permanently blinded a check that the project brief
lists as an MVP scenario. Thresholds get changed after diagnosis and with the
justifying measurement recorded, never to silence an alert.

**(c) Absolute accuracy is the wrong metric for SCADA.**
Led to ADR-002: monitor clock *agreement* between correlating systems rather
than deviation from an external reference. Full implementation gated on the
Proxmox cluster, since all Docker Desktop containers share one WSL2 kernel
clock and a peer-offset probe would return ~0 by construction.

**(d) Absence of a diagnostic tool is not absence of connectivity.**
Side finding during network verification: `docker exec caltest-ignition ping`
returned `executable file not found`. The Ignition image ships no `ping`. Test
reachability with `bash`'s `/dev/tcp` pseudo-device or a throwaway `--rm`
container that has tooling — and never read a missing binary as a network
failure.

---

## 9. Follow-up actions

| # | Action | Status |
|---|---|---|
| 1 | `w32time` set to Automatic + multi-peer list | Done |
| 2 | Re-check Root Dispersion after several poll cycles (was 7.8 s immediately post-sync; should tighten) | **Open** |
| 3 | Record measured bias + ADR-002 reference as a comment in `lab-a.yaml`; thresholds unchanged | **Open** |
| 4 | Add `peers:` block to `TimeSyncBaseline` and implement peer-offset probe | Gated on Proxmox cluster |
| 5 | Encode finding (a) as a rule when host/service collectors are built | Backlog |
| 6 | Verify `w32time` state survives a host reboot | **Open** |
