# Fabro-on-OpenShell Phase 1: findings & runbook

**Status: Phase 1 core loop proven (2026-07-08).** A real Fabro workflow
(`hello`, 3 nodes, agent node with tool use) completed end-to-end inside one
OpenShell sandbox under a default-deny policy with a minimal grant set, using
a Claude Code OAuth token that never entered the sandbox.

## Architecture of the working setup

```
host: openshell gateway (mise run gateway, Docker driver, 127.0.0.1:18080)
  └─ sandbox "fabro" (BYOC image: debian-slim + fabro binary + git + iproute2)
       ├─ policy: fabro-policy.yaml (this dir) — default-deny, per-binary rules
       ├─ fabro CLI → embedded fabro server (unix socket) → run workers
       ├─ all egress forced through in-sandbox policy proxy (10.200.0.1:3128)
       └─ Anthropic auth: OpenShell `anthropic` provider placeholder
          (openshell:resolve:env:…) stored in fabro's vault; the proxy
          rewrites it to the real OAuth token in-flight
```

## The five integration pitfalls (in the order they bite)

1. **Filesystem policy is static.** `/home/sandbox` must be in
   `read_write` at creation; fabro needs `~/.fabro`. Only
   `network_policies` hot-reload.
2. **Fabro's embedded server needs bootstrap config**: `server.auth.methods
   = ["dev-token"]`, `SESSION_SECRET`, `FABRO_DEV_TOKEN` (`fabro_dev_` + 64
   hex). In configured (non-wizard) mode the CLI still polls
   `~/.fabro/storage/server.dev-token` so we have to write the token there
   before we use the `fabro` CLI.
3. **Provider secrets must live in fabro's vault, not env** (workers are
   env-cleared). `fabro secret set CLAUDE_CODE_OAUTH_TOKEN <placeholder>` —
   the "secret" is just the OpenShell placeholder, so neither fabro's vault
   nor the sandbox ever holds the real credential.
4. **Workers lose the proxy env** (same env-clearing). Fix: generate
   `~/fabro-with-proxies` (re-export proxy/CA env, `exec /usr/local/bin/fabro`)
   and export `CARGO_BIN_EXE_fabro=/home/sandbox/fabro-with-proxies` (note the
   lowercase `fabro`!) before starting the server. Candidate upstream fix:
   add proxy/CA vars to `WORKER_ENV_ALLOWLIST` in
   `fabro-server/src/spawn_env.rs`.
5. **Claude OAuth tokens need the Bearer route.** Fabro's builtin
   `anthropic` provider sends `x-api-key`; a *custom-named* provider
   (`anthropic-oauth` in settings.toml here) uses Bearer auth, and
   `extra_headers` supplies `anthropic-beta: oauth-2025-04-20` +
   `anthropic-version`. Verified: api.anthropic.com accepts the Claude Code
   OAuth token in this shape.

## Runbook

```shell
# host: gateway
ulimit -n 500 && mise run gateway     # Docker driver, keeps running

# providers
openshell provider create --name anthropic --type claude --credential CLAUDE_CODE_OAUTH_TOKEN
openshell provider create --name github --type github --from-existing

# host: sandbox
openshell sandbox create --name fabro --from experiments/fabro-phase1 \
  --policy experiments/fabro-phase1/fabro-policy.yaml \
  --provider anthropic --provider github --no-tty -- true

# instance setup
openshell sandbox exec -n fabro -- bash -lc 'mkdir -p /sandbox/demo ~/.fabro/storage'

# git setup
cat << EOF | openshell sandbox exec -n fabro -- bash -lc 'cat - > ~/.gitconfig'
[user]
	email = $(git config get user.email)
	name = $(git config get user.name)
EOF

# fabro setup
# NB: upload dest is always a directory; the file is copied into that dir
openshell sandbox upload fabro experiments/fabro-phase1/settings.toml /home/sandbox/.fabro/.

# generate the worker wrapper from the live proxy env (pitfall #4):
# workers are env-cleared, so the wrapper re-exports proxy/CA vars and execs fabro.
# NB: exec command arguments must not contain newlines — pipe multi-line
# scripts through stdin (quoted heredoc: no host-side expansion).
cat << 'EOF' | openshell sandbox exec -n fabro -- bash -s
{ echo '#!/bin/sh'
  env | grep -iE '^(https?_proxy|all_proxy|no_proxy|ssl_cert_file|curl_ca_bundle|requests_ca_bundle|node_extra_ca_certs|deno_cert)=' | sed 's/^/export /'
  echo 'exec /usr/local/bin/fabro "$@"'
} > ~/fabro-with-proxies && chmod +x ~/fabro-with-proxies
EOF

cat << 'EOF' | openshell sandbox exec -n fabro --workdir /sandbox/demo -- bash -s
export SESSION_SECRET=$(head -c32 /dev/urandom | base64)
export FABRO_DEV_TOKEN=fabro_dev_$(head -c32 /dev/urandom | od -An -tx1 | tr -d ' \n')
echo "export SESSION_SECRET=${SESSION_SECRET}" > ~/fabro-env.sh
echo "export FABRO_DEV_TOKEN=${FABRO_DEV_TOKEN}" >> ~/fabro-env.sh
echo "export CARGO_BIN_EXE_fabro=/home/sandbox/fabro-with-proxies" >> ~/fabro-env.sh
printf %s "${FABRO_DEV_TOKEN}" > ~/.fabro/storage/server.dev-token
git init -q && fabro repo init
fabro secret set CLAUDE_CODE_OAUTH_TOKEN "$CLAUDE_CODE_OAUTH_TOKEN"
fabro secret set GITHUB_TOKEN "$GITHUB_TOKEN"
EOF

# watch governance (in another terminal window)
openshell logs fabro --tail --source sandbox     # OCSF allow/deny events

# run a workflow
openshell sandbox exec -n fabro --workdir /sandbox/demo -- bash -c 'source ~/fabro-env.sh && fabro run hello'

# ... and watch the tailing logs. You should see:
# * NET:OPEN [INFO] ALLOWED /usr/local/bin/fabro(94) -> api.anthropic.com:443
# * HTTP:POST [INFO] ALLOWED POST http://api.anthropic.com:443/v1/messages
# * DENIED /usr/local/bin/fabro(312) -> cdp.customer.io:443
```

## Approach-doc open questions — answers so far

1. **Fabro as unprivileged child under process policy?** Yes. CLI, embedded
   server (unix socket), SlateDB storage, and `local`-provider workers all
   run as the `sandbox` user under Landlock/seccomp. Web UI port-forward not
   yet tested.
2. **Real egress footprint?** Tiny for the api backend: `api.anthropic.com`
   (`POST /v1/messages*`) + `cdp.customer.io` telemetry (deniable). See
   DENIALS.md.
3. **MCP inspection of fabro's MCP traffic?** Not yet tested.
4. **ACP backend running Claude Code in-sandbox?** Not yet tested.
5. **Performance?** Sandbox cold start ≈1 s (image cached). `hello` run:
   16 s wall, 8.7 s inference, tool overhead 5 ms — proxy inspection cost is
   noise compared to inference.

## Bonus findings about OpenShell itself

- **Binary integrity pinning**: the proxy pins the first-seen sha256 per
  binary path and denies after a binary changes, across policy reloads.
  Great against tampering; remember it when iterating on uploaded tools.
- **Observability gap**: connections attempted *without* the proxy env die
  in the netns (DNS NXDOMAIN / SYN blackhole) with no OCSF event. A
  netns-level "attempted direct egress" signal would have cut hours off this
  debug. Candidate OpenShell issue.
- Fabro retries after a transport error are instant no-network failures
  (likely non-rewindable request body) — the retry loop can't recover from a
  first-attempt connection failure. Candidate Fabro issue.

## Phase 2 pointers

- The fork is still required for per-node sandboxes (`SandboxProviderKind`
  closed enum). This phase's wrapper/env findings shrink the fork surface:
  a `SandboxProvider` calling the gateway gRPC API needs no worker-env
  tricks (OpenShell injects env per sandbox).
- Upstreamable-to-fabro list: proxy vars in `WORKER_ENV_ALLOWLIST`;
  document `CARGO_BIN_EXE_fabro`; error chains in `fabro_llm` Display
  (the truncated "Network error" hid the root cause for hours).
