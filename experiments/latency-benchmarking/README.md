# Relay latency benchmarking

Companion material for [NVIDIA/OpenShell#2219](https://github.com/NVIDIA/OpenShell/issues/2219)
("~45 ms added latency on sandbox tunnels/egress tinygrams due to Nagle ×
delayed-ACK"). This is a **temporary branch** published so others can
reproduce the measurements on their own setups; it will be deleted once the
issue is resolved.

The harness isolates where time goes on the sandbox egress path by running
the same HTTPS workload at increasing levels of the stack (a "rung ladder"),
from inside a sandbox to a TLS echo server on the host.

## The rungs

| Rung | Path | Isolates |
|---|---|---|
| A | host → echo server, direct | machine floor (curl + TLS + loopback) |
| B | sandbox → egress proxy, L4 passthrough | tunnel/relay transport cost |
| C | sandbox → egress proxy, L7 terminate + inspect | TLS termination, header parse, policy eval, OCSF emit |
| D | C + placeholder `Authorization` header | credential placeholder rewrite |
| E | C + request-body credential rewrite | body scan/rewrite path |

Cells within each rung: `sizes` (1 KB → 10 MB request- and
response-direction sweeps, one request per connection), `keepalive` (1, 10,
and 100 requests over a single connection — the marginal per-request cost is
the per-request constant, with connection setup amortized away), and
`header` (1–12 KB header padding).

## Prerequisites

- A running OpenShell gateway (`mise run gateway:docker`) with the Docker
  compute driver, and the `openshell` CLI pointed at it
- `python3` and `openssl` on the host
- Port 8443 free on the host

## Run it

```shell
./run-ladder.sh 30
```

The argument is repetitions per cell (default 30). The script generates a
local throwaway CA on first run (`gen-ca.sh`), starts the echo server,
creates a `bench` sandbox from this directory's Dockerfile, runs rungs A–E,
and leaves CSVs in `results-v2/<timestamp>/`.

Analyze:

```shell
python3 analyze.py results-v2/<timestamp>
```

This prints per-cell medians/IQRs, fitted per-byte slopes, and the
keep-alive marginal per-request constants. All timings come from curl's
`-w` timers (`time_connect`, `time_appconnect`, `time_starttransfer`,
`time_total`), in seconds in the CSVs, reported as milliseconds by the
analyzer.

## Results in this branch

`results/` holds two complete runs from the same machine and day
(macOS 26.4.1 arm64, Docker Engine 29.5.3, Docker compute driver,
30 reps/cell):

- `baseline-main-420a855d/` — gateway + supervisor built from `main`
  @ 420a855d
- `fix-tcp-nodelay-300068ba/` — the same plus one commit setting
  `TCP_NODELAY` on all relay-path sockets
- `analysis-baseline.txt` / `analysis-fix.txt` — full analyzer output
- `RESULTS.md` — comparison write-up

Headline (medians over 30 reps): the marginal cost of a small
request/response over an established keep-alive connection drops from
~44 ms to ~0.3–0.5 ms — within a few hundred microseconds of the host
loopback floor — with no regression in any bulk-transfer or L7-rewrite
cell.
