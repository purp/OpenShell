# Phase 1 denial log

Every policy denial observed while running Fabro under OpenShell governance,
and the rule (if any) added to resolve it. This is the empirical requirements
list for Phase 2 per-node policies (approach doc §2, deliverable 3).

| # | When (UTC) | Binary | Destination | Request | Resolution |
|---|------------|--------|-------------|---------|------------|
| 1 | 2026-07-08 18:39 | /bin/bash | filesystem `/home/sandbox/.profile` | read (Landlock) | Added `/home/sandbox` to `filesystem_policy.read_write`. Static field → sandbox recreate required. Fabro needs `~/.fabro` writable. |
| 2 | 2026-07-08 18:41 | /usr/bin/curl | example.com:443 | CONNECT | None — deliberate probe confirming default-deny. |
| 3 | 2026-07-08 18:41 | /usr/bin/curl | api.anthropic.com:443 | CONNECT | None — probe confirming per-binary enforcement (endpoint allowed for `fabro`, not `curl`). Reason string names the policy and kernel-resolved binary path. |
| 4 | 2026-07-08 18:55–19:47 | /usr/local/bin/fabro | cdp.customer.io:443 | CONNECT (telemetry, fires per run) | **Left denied deliberately.** Fabro works fine with its telemetry blackholed; `FABRO_TELEMETRY=off` is the polite alternative. First entry in the empirical egress footprint. |
| 5 | 2026-07-08 19:37 | /home/sandbox/repro | api.anthropic.com:443 | CONNECT | Re-uploaded (recompiled) binary denied: **binary integrity pinning** — the proxy caches the first-seen sha256 per path and denies on change, surviving policy reloads. Debugging artifact, removed from final policy. |

## Not-a-denial, but the biggest governance finding

Fabro spawns run workers with `env_clear()` + a strict allowlist
(`fabro-server/src/spawn_env.rs`). Workers therefore lose `HTTPS_PROXY`/CA
env vars, and OpenShell's network namespace blackholes direct egress: DNS
fails instantly (≈12 ms `Network error`), and `/etc/hosts` names hang to the
30 s connect timeout. No OCSF denial is logged because no packet ever reaches
the proxy — an observability gap worth noting for Phase 2 (the sandbox knows
nothing about connections that die in the netns).

Workaround (no fork needed): a wrapper script that re-exports the proxy/CA
env and `exec`s the real binary, activated via fabro's worker-executable
override env var `CARGO_BIN_EXE_fabro` (lowercase binary name — cargo
convention). Policy binary identity is unaffected because the kernel-resolved
`/proc/<pid>/exe` is still the real fabro binary.

## Final egress footprint (fabro `hello` workflow, api backend)

- `api.anthropic.com:443` — `POST /v1/messages` (+ `count_tokens`), binary `/usr/local/bin/fabro`
- `cdp.customer.io:443` — telemetry, denied without harm
- `github.com:443` — not exercised by `hello`; rules staged for git fetch only
