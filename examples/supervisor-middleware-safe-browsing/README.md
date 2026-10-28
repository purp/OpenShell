<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Safe Browsing supervisor middleware proof of concept

This experimental service checks admitted HTTP requests against Google Safe
Browsing v5 and denies requests with a reported threat. It implements the existing
OpenShell supervisor middleware protocol; it requires no gateway, supervisor, or
provider changes. Treat this example as a development prototype.

## How it works

1. OpenShell admits a request through its existing network policy.
2. Request middleware receives the destination, path, and query before provider
   credential injection.
3. This service calls Google's `GET /v5/urls:search` with one URL. Google performs
   canonicalization and host-suffix/path-prefix threat matching.
4. Any returned threat denies the request with `safe_browsing_threat`. Empty
   results allow it. This example blocks all reported threat categories.
5. The service caches both outcomes for the response's `cacheDuration`, keyed by
   the complete URL. It never caches errors or extends the returned lifetime.

The cache holds at most 4,096 entries in process memory. On capacity exhaustion it
clears the cache and resumes live checks. Up to 64 live lookups may run at once;
additional misses fail instead of queueing. Concurrent misses for the same URL
can produce duplicate lookups. Each lookup has a total timeout (2 seconds by
default), a 256 KiB response limit, and no redirects. The client uses public WebPKI
roots through `openshell-crypto` and disables environment-configured HTTP proxies.

The Google API key stays in the service process. No API key is needed in sandbox
policy or the agent environment. The service does not log lookup URLs, response
bodies, API keys, or underlying HTTP client errors. OpenShell's existing middleware
path emits decision and finding events.

## Run without a Google API key

From the repository root:

```shell
cargo test --manifest-path examples/supervisor-middleware-safe-browsing/Cargo.toml
```

The tests use a local mock Google API. The `grpc_service_blocks_threats_and_fails_closed_on_outage`
test starts the actual gRPC service, registers it through OpenShell's middleware
registry, and drives the middleware chain through clean, threat, and API-outage
responses. Other tests cover URL handling, cache expiry/capacity, timeouts,
redirect refusal, malformed responses, and secret-free errors. No sandbox or
container runtime is required for these tests.

## Run with Google Safe Browsing

Enable the Safe Browsing API in a Google Cloud project and obtain an API key.
Set `SAFE_BROWSING_API_KEY` in the service process environment, then start the
service from the repository root:

```shell
cargo run --manifest-path examples/supervisor-middleware-safe-browsing/Cargo.toml -- --bind 0.0.0.0:50052
```

The default listener is `127.0.0.1:50052`; the command above binds all interfaces
so development gateway and sandbox containers can reach it. This prototype uses
plaintext gRPC without peer authentication. Run it only on a trusted development
network. It does not verify gateway bearer tokens or implement service TLS.

Merge the registration in [gateway.toml](gateway.toml) into your gateway's TOML
configuration, replace its hostname with an address reachable from **both** the
gateway and sandbox supervisors, and restart the gateway. The registration
requires the HTTP request binding with `binding_policy = "exact"`; a service
upgrade cannot silently replace request inspection with response-only inspection.
The middleware RPC timeout is 3 seconds, longer than the default Google timeout.
Start the service before the gateway because the gateway negotiates its protocol
at startup.

Create a sandbox with the example policy:

```shell
openshell sandbox create --name safe-browse-poc --policy examples/supervisor-middleware-safe-browsing/policy.yaml --no-tty --detach -- sleep infinity
```

Try a clean navigation and Google's malware demonstration URL:

```shell
openshell sandbox exec --name safe-browse-poc --no-tty -- curl -i https://example.com/
openshell sandbox exec --name safe-browse-poc --no-tty -- curl -i https://testsafebrowsing.appspot.com/s/malware.html
```

The first should reach the destination if Google returns no threat. The second
should receive an OpenShell `403` with `error: middleware_denied` and
`reason_code: safe_browsing_threat` when Google reports a threat. Live results
depend on Google's current data and the API key's quota and authorization.
A Google error or timeout is a middleware failure rather than a threat match;
`on_error: fail_closed` blocks that request too. A previously cached unexpired
result remains usable during an outage.

For a Google denial, interpret `safe_browsing_threat` as **potentially unsafe**,
not proof of maliciousness. Advisory provided by Google:
[Google Safe Browsing Advisory](https://safebrowsing.google.com/).
[Learn about malware and unwanted software](https://developers.google.com/search/docs/monitor-debug/security/malware)
and [social engineering](https://developers.google.com/search/docs/monitor-debug/security/social-engineering).
OpenShell sanitizes external middleware diagnostics, so its canonical denial
response retains the reason code rather than forwarding this service's free-form
advisory text. Any UI built on this example must display the Google attribution,
advisory link, and qualified warning when showing Google-derived threat denials.

The policy permits only `curl` GET requests to the two demonstration hosts. To
try other navigation destinations, add them to both `network_policies` and the
middleware's `endpoints.include`. Middleware cannot grant access that policy
otherwise denies. Keep `on_error: fail_closed` and TLS inspection enabled.
Stop the middleware and retry an uncached URL to exercise fail-closed behavior.
Delete the sandbox after trying it:

```shell
openshell sandbox delete safe-browse-poc
```

## Boundaries and follow-ups

- **Full URL disclosure:** `urls.search` sends full paths and query strings to
  Google, including any secrets already present in the request target. OpenShell
  provider credentials are injected later, but application-supplied query secrets
  can already be present. The service also holds URLs in its memory cache.
- **No OHTTP:** this prototype uses direct HTTPS lookups. A privacy-preserving
  implementation should use Google's canonicalization/expression rules,
  `hashes.search`, and optionally an independent OHTTP relay. Google seeing a
  service IP rather than an agent IP does not provide OHTTP's privacy properties.
- **Request blocking:** the current supervisor can establish upstream TCP/TLS
  before invoking request middleware. A denial prevents forwarding the HTTP
  request; it does not promise that no packet reached the destination. Preventing
  any contact requires an earlier connection gate and deferred upstream dialing.
- **Inspection coverage:** opaque TLS tunnels (`tls: skip`), QUIC, arbitrary TCP,
  and traffic outside the middleware selector do not receive URL checks. Required
  inspection needs a policy that blocks alternative paths. This service advertises
  only HTTP request inspection, not WebSocket message or response inspection.
- **Conservative URL parsing:** ambiguous targets, literal fragments, dot segments
  rewritten by the URL parser, non-ASCII targets, and URLs over 16 KiB fail as
  middleware errors. This avoids silently checking a different URL. This is not a
  complete browser URL handling implementation.
- **No safety guarantee:** Google can return both false positives and false
  negatives. An unlisted page can contain malware or prompt injection. Continue
  using network policy and other sandbox controls.
- **Google usage limits:** Safe Browsing is noncommercial only. Google describes
  navigation URLs, including redirects, as the appropriate scope and says not to
  check subresources such as scripts, images, or WebSockets. A general middleware
  cannot reliably infer browser navigation from arbitrary agent requests. Use
  this example for controlled navigation experiments, not a blanket production
  egress filter. Evaluate Google Web Risk for commercial deployments.

See the official [v5 URL lookup API](https://developers.google.com/safe-browsing/reference/rest/v5/urls/search),
[appropriate usage guidance](https://developers.google.com/safe-browsing/reference/Appropriate.Usage),
and [OHTTP gateway documentation](https://developers.google.com/safe-browsing/ohttp/reference).

The `--api-endpoint` flag accepts an alternative HTTPS backend or loopback HTTP
mock. It is service-operator configuration, not sandbox policy; never point it at
an untrusted backend because it receives the API key and lookup URLs. The backend
must implement the v5 URL lookup response contract. OHTTP and Web Risk are not
drop-in endpoint changes.
