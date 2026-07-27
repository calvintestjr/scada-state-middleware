# ADR-002: Monitor Clock Agreement, Not Clock Accuracy

**Status:** Accepted (partially deferred) — 2026-07-26
**Deciders:** Calvin (owner), Claude (Senior Infrastructure Architect)
**Supersedes:** nothing. **Related:** ADR-001, `docs/drills/M1-ntp-detection.md`

## Context

The MVP `ntp_offset` probe measures the collector container's clock against a
public NTP server (`pool.ntp.org`) and classifies the absolute offset against
a policy threshold (`max_offset_ms: 250`).

On first run this probe opened three incidents in ~30 minutes. All three were
true positives (see drill doc), rooted in the Windows host's `w32time` service
being Stopped/Manual and therefore not disciplining the clock at all. After
remediation, measured offset settled at **158–166 ms** — stable, ~8 ms spread,
no drift — against a properly synchronized Stratum 2 host.

That residual ~160 ms is not clock error. It is measurement bias from the
path: collector container → Docker NAT → WSL2 virtual NIC → Windows host
network stack → public internet. SNTP derives offset assuming a symmetric
round trip; asymmetry inflates the result by roughly half the difference.

This exposed a modelling question the absolute-offset check does not answer:
**what does time correctness actually mean for SCADA/OT?**

## Decision

**Monitor clock *agreement* between the systems that must correlate, not
absolute UTC accuracy.**

In an industrial context, absolute accuracy is a proxy metric. The real
operational requirement is that the Gateway, the historian/alarm journal, the
OPC server, and the PLCs share a common reference — so that an alarm at
23:40:14.3 can be correlated against a PLC event at 23:40:14.1 and the
ordering means something. A site whose clocks are all 400 ms off the same NIST
reference is operationally fine. A site whose Gateway and historian disagree
by 400 ms with each other has corrupt event ordering, even if both are within
policy of an external server.

This reframes the probe from "am I accurate?" to "do the parties to a
correlation agree?"

## Deferred: peer-offset implementation is gated on hardware

The full form of this decision — pairwise clock comparison between hosts — is
**not implementable on the current platform and must not be faked.**

All containers on Docker Desktop share a single underlying WSL2 kernel clock.
A peer-offset probe comparing `mw-collector` to `caltest-ignition` would
return values near zero by construction, regardless of the true state of
either clock or of the host. That is worse than no probe: it would manufacture
false confidence in a check that cannot fail.

**Gate:** peer-offset comparison is implemented when the Proxmox cluster
provides genuinely separate physical hosts (three-node build: ProDesk 600 G4,
OptiPlex 7050, HPE ProLiant). At that point `time_sync` gains a `peers:` block
and the probe compares node clocks pairwise, classifying on divergence
*between* peers rather than deviation from an external server.

## Interim decision: retain the absolute check unchanged

`max_offset_ms` stays at **250** and `critical_offset_ms` stays at **2000**.

Explicitly *not* raised to absorb the 160 ms measurement bias, for three
reasons:

1. **Current measurements pass with headroom.** 158–166 ms against a 250 ms
   threshold. The check is quiet because the environment is healthy, not
   because it was tuned to be quiet.
2. **Every incident it raised was a true positive.** False-positive rate to
   date: zero. Raising the threshold on first fire would have masked a real
   2.4-second clock fault and prevented discovery of the disabled service.
3. **The bias is platform-specific and temporary.** It is an artifact of
   Docker Desktop NAT on Windows. It disappears when collection moves to the
   Proxmox cluster, so encoding it into policy would embed a constant that is
   already scheduled to become wrong.

If the residual bias later pushes measurements past 250 ms, the correct
response is a documented `approved_deviation` for this site with the
justifying measurement attached — not a silent threshold change.

## Consequences

- `desired-state/sites/lab-a.yaml` gains a comment recording the measured
  bias, its cause, and the ADR reference. Thresholds are unchanged.
- A `peers:` schema addition to `TimeSyncBaseline` is scheduled but not built.
  No placeholder probe is shipped.
- Detection logic gains a durable requirement from the drill (below): time
  health must be assessed on **Leap Indicator and Stratum**, never on a
  "last successful sync" timestamp. When SNMP/host collectors arrive, this is
  a schema-level rule, not probe-local trivia.
- The platform limitation is documented rather than worked around. "This
  monitor cannot meaningfully check peer clock agreement on its current
  host, and here is why" is a stronger position than a probe that always
  returns zero.
