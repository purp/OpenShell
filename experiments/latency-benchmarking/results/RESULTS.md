# TCP_NODELAY fix — A/B benchmark results (2026-07-10)

Clean A/B on the same machine, same day, full rung ladder, 30 reps/cell.
**All numbers are medians over 30 repetitions per cell**; IQRs are in the
full analyzer output (`analysis-baseline.txt`, `analysis-fix.txt`).

- **Baseline:** gateway + supervisor built from `main` @ `420a855d`
  (raw CSVs: `baseline-main-420a855d/`)
- **Fix:** the same plus one commit setting `TCP_NODELAY` on all
  relay-path sockets (raw CSVs: `fix-tcp-nodelay-300068ba/`)

Environment: macOS 26.4.1 (arm64), Docker Engine 29.5.3 (linux/arm64),
Docker compute driver, standalone gateway via `mise run gateway:docker`,
debian-slim + curl sandbox, TLS echo server on host.

## Headline: keep-alive marginal cost per small request

Median of per-request totals for requests after the first on a single
keep-alive connection (connection setup amortized away):

| Rung | baseline | fix | host floor (rung A) |
|---|---|---|---|
| B (L4 passthrough), 10-req conn  | 44.39 ms | **0.33 ms** | 0.09 ms |
| B (L4 passthrough), 100-req conn | 43.58 ms | **0.27 ms** | 0.06 ms |
| C (L7 terminate+inspect), 10-req conn  | 45.49 ms | **0.49 ms** | 0.09 ms |
| C (L7 terminate+inspect), 100-req conn | 44.49 ms | **0.45 ms** | 0.06 ms |

~99% reduction (≈130–160×). The L7 inspection stack (TLS termination,
header parse, policy eval, OCSF emit, credential rewrite) measures on the
close order of 200 µs per request over L4 passthrough (0.45 vs 0.27 ms
keep-alive marginal; single-shot 1 KB medians differ by ~20 µs) —
effectively 0 at millisecond scale.

## Single-shot small exchanges (TLS connect + 1 request)

| Cell | baseline | fix |
|---|---|---|
| B resp 1 KB | 62.64 ms | 14.66 ms |
| B req 1 KB  | 61.07 ms | 14.64 ms |
| C resp 1 KB | 62.52 ms | 14.68 ms |
| B ka1 (setup + 1 req) | 62.84 ms | 14.50 ms |

The remaining ~14.5 ms is TLS handshake + CONNECT setup
(`time_appconnect` ≈ 13 ms) — per-connection, not per-request. The
baseline's size inversion (1 KB slower end-to-end than 100 KB) is gone.

## Regression check: bulk payloads and L7 rewrite rungs

| Cell | baseline | fix | verdict |
|---|---|---|---|
| B resp 10 MB | 58.57 ms | 58.42 ms | unchanged |
| C resp 10 MB | 59.04 ms | 58.96 ms | unchanged |
| B req 10 MB  | 90.41 ms | 46.09 ms | **2× faster** |
| B req 1 MB   | 63.73 ms | 18.07 ms | 3.5× faster |
| D resp/req 1 KB (placeholder header) | 64.6 / 63.5 ms | 14.8 / 14.8 ms | tracks C |
| E resp/req 1 KB (body rewrite) | 63.7 / 63.5 ms | 14.7 / 14.8 ms | tracks C |

No cell regressed. Request-direction bulk transfers were also
Nagle-throttled: 10 MB uploads through the tunnel got 2× faster.

Per-byte throughput at 10 MB is unchanged in the response direction; the
fitted ns/byte figure rises (2.3 → 4.2) only because the intercept
collapsed (33 → 15 ms) while the 10 MB total stayed put — an artifact of
the linear fit, not a throughput loss.
