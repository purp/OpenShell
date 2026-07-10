# Proxy-inspection cost benchmarks

Question: how does OpenShell's L7 inspection cost scale with traffic volume?
Hypothesis: roughly linear in bytes (TLS termination + header scan dominate),
with a small per-request constant.

## Method

A matrix of single-node fabro workflows against the default model (Haiku via
`claude-oauth`), varying the two byte-volume knobs independently:

- **Request size**: quote-free filler text embedded in the prompt
  (~1KB / ~16KB / ~64KB)
- **Response size**: requested output length (~100 / ~1000 words)

Each node is tool-free ("reply in chat only") so byte volume is the only
variable — no agentic loop variance. Regress non-inference overhead against
request+response bytes; the slope is the marginal proxy cost per byte, the
intercept the per-request constant.

## Why there is no "inspection off" control arm

You cannot A/B L7-inspected vs L4-passthrough here: the OpenShell credential
placeholder (`openshell:resolve:env:...`) is rewritten to the real token by
the proxy **inside the TLS-terminated stream**. Turn off termination and auth
itself breaks. Governed placeholder credentials and uninspected traffic are
mutually exclusive by design — a finding in its own right.

So this benchmark measures *scaling within* the inspected path, not
inspected-vs-not. If an absolute baseline is ever needed, run the same
payloads against `POST /v1/messages/count_tokens` from the host (outside the
sandbox) and compare curves.

## Caveats

- `wall_ms` in results.csv includes a constant `openshell sandbox exec`
  round-trip; compare deltas, not absolutes.
- Inference time is the dominant, high-variance term (generation length,
  server load). Use fabro's own timing breakdown from the run logs
  (inference vs tool vs wall) and multiple reps; medians over means.
- Output length is approximate — the model targets the requested word count
  loosely. The logs record actual token usage when fabro reports it.

## Running

```shell
./gen-workflows.sh        # writes workflows/<bench-inNk-outM>/
./run-bench.sh [reps]     # uploads workflows, runs matrix, writes results/
```

Prereqs: gateway up, `fabro` sandbox created and set up per
[../NOTES.md](../NOTES.md). `workflows/` and `results/` are gitignored
(generated artifacts).

## First results (2026-07-09, 3 reps, median wall ms)

| | out ~100 words | out ~1000 words |
|---|---|---|
| **in ~1KB** | 6525* | 17669 |
| **in ~16KB** | 3698 | 17746 |
| **in ~64KB** | 3217 | 18222 |

\* one 3161ms rep; the two slow reps look like server-side variance, not size.

Takeaways:

- **Request size is free at these scales.** 1KB → 64KB (64× the inspected
  request bytes, ~16k extra prompt tokens) produces no measurable wall-time
  increase — the 64KB cell is actually the fastest out-100 cell. Proxy
  inspection cost on the request path is below the inference noise floor.
- **Response size dominates** (~3.5s → ~18s for 100 → 1000 words), and that
  is generation time, not proxy time — the proxy relays the response stream
  without per-byte rule matching.
- So: "roughly linear in bytes" may still be true of the proxy in isolation,
  but the slope is so shallow that it is invisible next to inference. At
  workflow scale, proxy inspection cost is noise. Larger payloads (MB-scale
  request bodies) would be needed to surface a measurable slope.
