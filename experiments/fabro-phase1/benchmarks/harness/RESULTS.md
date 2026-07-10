# v2 ladder results (2026-07-09, 30 reps/cell, medians)

Host: macOS + Docker Desktop; echo server on host; sandbox = debian-slim +
curl. Raw data in `results-v2/` (gitignored). Fit with `analyze.py`.

## Fitted model

| Term | Prediction (PLAN.md) | Measured | Verdict |
|---|---|---|---|
| per-byte, L4 (B) | — | ~2.3-2.4 ns/B (~2.4 µs/KB), both directions | baseline |
| per-byte, L7 (C) | 1-3 µs/KB | ~2.3-2.5 ns/B — **≈ L4** | H3 magnitude ✓; termination adds no measurable per-byte |
| per-request (keep-alive marginal) | 0.1-1 ms | **~45 ms** (B *and* C) | H2 ✗ — dominated by a transport artifact, see below |
| per-connection (ka1 − marginal) | low ms | ~21 ms (incl. 2× TLS handshake ~20 ms appconnect + CONNECT identity) | H1 roughly ✓ |
| header size 1→12 KB (C) | visible slope | ≤2 ms, under noise | byte-at-a-time parser invisible |
| D placeholder header vs C | small | no measurable delta @30 reps | rewrite is free at ms scale |
| E body rewrite ≤100 KB vs C | visible step | no measurable delta @30 reps | free at ms scale |
| host floor (A) | — | 0.8 ms connect+request; 0.06 ms marginal/request | reference |

## The two real findings (both filed in Linear)

1. **Expect: 100-continue deadlock (MEY-32).** Uploads >1 MB with curl
   defaults hang forever through the tunnel — even L4 passthrough. Found
   because the 10 MB request cell hung; harness works around it with
   `-H 'Expect:'`.
2. **~45 ms small-exchange penalty in the tunnel (MEY-33).** Every
   request/response over an established tunnel costs ~45 ms (plain-Docker
   control: 15-20 ms; host floor: 0.06 ms) regardless of L4 vs L7. TTFB is
   2-3 ms — the stall is on the small response tail. 40-45 ms quantum that
   disappears with payload volume = Nagle × delayed-ACK signature, and
   `openshell-supervisor-network` never sets `TCP_NODELAY` on accepted or
   upstream sockets.

## Interpretation

- **Inspection is cheap; the tunnel's small-packet behavior is not.** The
  entire L7 stack (TLS termination, byte-at-a-time header parse, Rego eval,
  OCSF emit, placeholder rewrite, body rewrite) measures ≈ 0 against L4 at
  30-rep resolution — everything is hidden under the 45 ms artifact, which
  affects L4 equally and is likely fixable (TCP_NODELAY / flush discipline).
- **Per-byte cost is ~2.4 µs/KB** through the sandbox (vs ~5 µs/KB on the
  loopback host floor with macOS curl — different TLS stacks; compare
  slopes only within a path). 10 MB moves through the tunnel in ~60-90 ms.
- Back-prop to v1: a Haiku workflow call (~KB-scale exchange) carries
  roughly one 45 ms penalty + ~21 ms connection setup — ~0.4% of a 16 s
  workflow run. Consistent with v1's null result.
- Answer to the original question ("linear in traffic?"): yes, but the
  slope is 2.4 µs/KB — per-connection and per-request constants dominate
  until payloads reach ~10 MB, and today those constants are set by a
  fixable transport artifact, not by inspection.
