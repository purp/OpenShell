# Proxy-inspection benchmark: hypothesis & measurement plan

Replaces the v1 "vary Haiku prompt sizes" design, which measured end-to-end
wall time dominated by inference and could not attribute anything to the
proxy. This plan starts from the proxy source and predicts each cost before
measuring it.

## Cost model from the code (openshell-supervisor-network)

The data path has three cost classes with different scaling:

### Per-CONNECT (one TCP connection / CONNECT tunnel)

- procfs identity resolution: `/proc/<pid>/net/tcp` inode scan, ancestor
  chain walk reading `/proc/<pid>/exe`, cmdline collection
  (`proxy.rs:1437-1495`)
- binary integrity: `stat` + fingerprint compare per binary *and per
  ancestor* (`identity.rs:106-131`); **full-file SHA256 only on first
  sighting** of a (path, fingerprint) — cost scales with binary size, paid
  once per sandbox lifetime (`identity.rs:139`)
- L4 Rego eval + regorus engine clone for the tunnel (`opa.rs:615-627`)
- **two TLS handshakes** — client-side termination + fresh upstream
  connection; no cross-connection upstream pooling (`proxy.rs:1131-1133`)
- DNS + upstream TCP connect, CONNECT OCSF event

### Per-REQUEST (keep-alive loop; every request pays all of this)

- **byte-at-a-time header read** (anti-smuggling, `read_u8` loop,
  `rest.rs:151`, cap 16 KiB) + UTF-8/bare-LF scans + query-param HashMap
- placeholder rewrite of the **header block only** + fail-closed re-scan of
  `header_end+256` bytes (`rest.rs:481`, `secrets.rs:973`)
- serde_json input build + `.to_string()` + tunnel-engine mutex +
  `eval_rule` (glob matching happens *inside* each Rego eval — not
  precompiled) (`relay.rs:1608-1656`)
- OCSF HttpActivity event **built and synchronously emitted for every
  request, including allows** (`rest.rs:883-899`)

### Per-BYTE (body relay)

- 8 KiB chunked copy loop (`RELAY_BUF_SIZE`, `rest.rs:30`) + atomic
  staleness check per read
- double TLS crypto (decrypt client-side, re-encrypt upstream)
- **request bodies are NOT scanned** unless the endpoint opts into
  `request_body_credential_rewrite` (then buffered ≤256 KiB, `rest.rs:795`)
- **response bodies are NEVER scanned** — status line + headers parsed,
  body blind-relayed (`rest.rs:1917-2072`)

## Hypotheses (falsifiable, with predicted magnitudes)

- **H1** Per-CONNECT constant is the dominant proxy cost: low-single-digit
  ms (2× TLS handshake + procfs walks), plus a one-time first-use spike per
  binary proportional to binary size (SHA256 at ~1-2 GB/s: ~40-80 ms for an
  ~80 MB binary).
- **H2** Per-request constant is O(0.1-1 ms) and scales ~linearly with
  *header* bytes (byte-at-a-time parser) and with policy rule count (Rego
  eval); it does not depend on body size.
- **H3** Per-byte cost is ~1-3 µs/KB (double AES-GCM + copy), the same for
  request and response directions, independent of policy complexity.
  Corollary: v1's 64 KB request bodies predicted only ~100-200 µs of proxy
  time — unmeasurable under seconds of inference, as observed.
- **H4** Enabling `request_body_credential_rewrite` adds a measurable step
  (buffer + scan) on request bodies up to 256 KiB.

## Measurement design

Model excluded entirely. Destination = TLS echo server on the host
(fixed instant responses, sized request sink + sized response source).
Sandbox needs an `allowed_ips` policy entry if the host resolves to a
private IP (SSRF guard blocks RFC1918 by default).

Component ladder — each rung adds one term:

| Rung | Setup | Isolates |
|---|---|---|
| A | host → echo server, direct | network + TLS floor |
| B | in-sandbox curl → echo, **L4** policy (no protocol) | netns + relay + CONNECT identity costs |
| C | + `tls: terminate`, `protocol: rest`, one allow rule | double-crypto + parse + eval |
| D | + placeholder header on the request | header rewrite + fail-closed scan |
| E | + `request_body_credential_rewrite` | opt-in body scan (H4) |

Factor sweeps (each isolates one model term):

1. **Requests per connection** (1, 10, 100 via keep-alive) → separates
   per-CONNECT from per-request constants (H1 vs H2).
2. **Header size** (1-16 KiB padding header) → per-request byte slope of
   the `read_u8` parser (H2).
3. **Body size, each direction independently** (1 KB → 10 MB request-only,
   then response-only) → per-byte slope (H3). MB-scale needed: at ~2 µs/KB,
   10 MB predicts ~20 ms — comfortably measurable.
4. **Policy rule count** (1, 10, 100 allow rules) → Rego eval scaling (H2).
5. **Cold vs warm binary** (first CONNECT from a freshly-uploaded large
   binary vs subsequent) → SHA256 spike (H1); vary binary size.

Instrumentation: `curl -w` phase timings (`time_connect`,
`time_appconnect`, `time_starttransfer`, `time_total`) separate handshake /
first-byte / transfer per rung.

## Statistics

- ≥30 reps per cell; cells **interleaved in randomized order**, not
  blocked, so drift doesn't alias as a size effect
- unique payload bytes per rep (no cache aliasing anywhere)
- cold/warm connection tracked as an explicit factor, never mixed
- report medians + IQR and the raw distributions; fit slopes on medians;
  declare an effect only if it exceeds the IQR and matches a predicted
  magnitude within ~3×

## Role of the v1 Haiku workflows

Demoted to an end-to-end realism check: after the component model is fit,
predict the proxy's contribution to a real workflow run and confirm the
end-to-end numbers are consistent with it. v1's result stands as: "at
workflow scale, end-to-end time is inference-dominated" — true but not a
proxy measurement.
