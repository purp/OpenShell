// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

//! Experimental direct URL lookup middleware. This sends full URLs to Google.

use std::collections::HashMap;
use std::net::SocketAddr;
use std::time::Duration;

use clap::Parser;
use openshell_core::middleware::WebSocketResponseStream;
use openshell_core::proto::middleware::v1::supervisor_middleware_server::{
    SupervisorMiddleware, SupervisorMiddlewareServer,
};
use openshell_core::proto::{
    Decision, Finding, HttpRequestEvaluation, HttpRequestResult, HttpRequestTarget,
    MiddlewareBinding, MiddlewareDescribeRequest, MiddlewareManifest,
    SupervisorMiddlewareOperation, SupervisorMiddlewarePhase, ValidateConfigRequest,
    ValidateConfigResponse, WebSocketSessionEvent,
};
use reqwest::{Client, Url};
use serde::Deserialize;
use tokio::sync::{Mutex, Semaphore};
use tokio::time::Instant;
use tonic::{Request, Response, Status};

const MANIFEST_NAME: &str = "example/safe-browsing";
const API_ENDPOINT: &str = "https://safebrowsing.googleapis.com/v5/urls:search";
const MAX_PAYLOAD_BYTES: u64 = 4 * 1024 * 1024;
const MAX_RESPONSE_BYTES: usize = 256 * 1024;
const MAX_URL_BYTES: usize = 16 * 1024;
const MAX_CACHE_ENTRIES: usize = 4096;

#[derive(Parser)]
#[command(about = "Experimental Google Safe Browsing v5 middleware (full URL lookups)")]
struct Cli {
    /// Plaintext gRPC listener. Use only on a trusted development network.
    #[arg(long, default_value = "127.0.0.1:50052")]
    bind: SocketAddr,
    /// Lookup endpoint; HTTP is permitted only for loopback test fixtures.
    #[arg(long, default_value = API_ENDPOINT)]
    api_endpoint: String,
    /// Total lookup timeout, including reading the response. Keep below the middleware RPC timeout.
    #[arg(long, default_value_t = 2000, value_parser = clap::value_parser!(u64).range(1..=25000))]
    timeout_ms: u64,
}

struct CacheEntry {
    unsafe_url: bool,
    expires: Instant,
}

struct SafeBrowsing {
    client: Client,
    endpoint: Url,
    cache: Mutex<HashMap<String, CacheEntry>>,
    lookups: Semaphore,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct LookupResponse {
    // Proto JSON may omit empty repeated fields, but a missing duration is an error.
    #[serde(default)]
    threats: Vec<Threat>,
    cache_duration: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Threat {
    url: String,
    threat_types: Vec<String>,
}

impl SafeBrowsing {
    fn new(endpoint: String, api_key: &str, timeout: Duration) -> Result<Self, Status> {
        let endpoint = Url::parse(&endpoint)
            .map_err(|_| Status::invalid_argument("invalid lookup endpoint"))?;
        let loopback = endpoint.host_str().is_some_and(|host| {
            host == "localhost"
                || host
                    .trim_matches(['[', ']'])
                    .parse::<std::net::IpAddr>()
                    .is_ok_and(|ip| ip.is_loopback())
        });
        if !(endpoint.scheme() == "https" || endpoint.scheme() == "http" && loopback)
            || !endpoint.username().is_empty()
            || endpoint.password().is_some()
            || endpoint.query().is_some()
            || endpoint.fragment().is_some()
        {
            return Err(Status::invalid_argument(
                "lookup endpoint requires HTTPS or loopback HTTP without userinfo, query, or fragment",
            ));
        }
        if api_key.trim().is_empty() {
            return Err(Status::invalid_argument(
                "SAFE_BROWSING_API_KEY must be non-empty",
            ));
        }
        let mut key = reqwest::header::HeaderValue::from_str(api_key)
            .map_err(|_| Status::invalid_argument("invalid SAFE_BROWSING_API_KEY"))?;
        key.set_sensitive(true);
        let mut headers = reqwest::header::HeaderMap::new();
        headers.insert("x-goog-api-key", key);
        // First-party TLS configuration goes through openshell-crypto. reqwest
        // owns the HTTP transport; protocol types and root data are not crypto implementations.
        let roots =
            rustls::RootCertStore::from_iter(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());
        let tls = openshell_crypto::tls::client_builder()
            .with_root_certificates(roots)
            .with_no_client_auth();
        let client = Client::builder()
            .use_preconfigured_tls(tls)
            .default_headers(headers)
            .redirect(reqwest::redirect::Policy::none())
            .no_proxy()
            .tcp_nodelay(true)
            .timeout(timeout)
            .build()
            .map_err(|_| Status::internal("could not initialize lookup client"))?;
        Ok(Self {
            client,
            endpoint,
            cache: Mutex::new(HashMap::new()),
            lookups: Semaphore::new(64),
        })
    }

    async fn check(&self, url: &str) -> Result<bool, Status> {
        if let Some(entry) = self.cache.lock().await.get(url)
            && entry.expires > Instant::now()
        {
            return Ok(entry.unsafe_url);
        }
        let _permit = self
            .lookups
            .try_acquire()
            .map_err(|_| Status::resource_exhausted("Safe Browsing lookup capacity exhausted"))?;
        let mut response = self
            .client
            .get(self.endpoint.clone())
            .query(&[("urls", url)])
            .send()
            .await
            .map_err(|_| Status::unavailable("Safe Browsing lookup failed or timed out"))?;
        // Never expose reqwest errors, response bodies, or request URLs: these may contain secrets.
        if response.status() != reqwest::StatusCode::OK {
            return Err(Status::unavailable(
                "Safe Browsing returned a non-200 response",
            ));
        }
        let mut body = Vec::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|_| Status::unavailable("Safe Browsing response failed or timed out"))?
        {
            if body.len().saturating_add(chunk.len()) > MAX_RESPONSE_BYTES {
                return Err(Status::unavailable("Safe Browsing response exceeds limit"));
            }
            body.extend_from_slice(&chunk);
        }
        let result: LookupResponse = serde_json::from_slice(&body)
            .map_err(|_| Status::unavailable("invalid Safe Browsing response"))?;
        let ttl = cache_duration(&result.cache_duration)?;
        if result.threats.iter().any(|threat| {
            threat.url.is_empty()
                || threat.threat_types.is_empty()
                || threat.threat_types.iter().any(String::is_empty)
        }) {
            return Err(Status::unavailable("invalid Safe Browsing threat entry"));
        }
        // A response can match a parent host/path expression rather than the
        // original URL. Every returned threat applies to this single-URL lookup.
        let unsafe_url = !result.threats.is_empty();
        let expires = Instant::now()
            .checked_add(ttl)
            .ok_or_else(|| Status::unavailable("invalid Safe Browsing cache duration"))?;
        if !ttl.is_zero() {
            let mut cache = self.cache.lock().await;
            cache.retain(|_, entry| entry.expires > Instant::now());
            if cache.len() >= MAX_CACHE_ENTRIES {
                cache.clear(); // Bounded POC cache: eviction can only cause another lookup.
            }
            cache.insert(
                url.to_owned(),
                CacheEntry {
                    unsafe_url,
                    expires,
                },
            );
        }
        Ok(unsafe_url)
    }
}

fn cache_duration(value: &str) -> Result<Duration, Status> {
    let invalid = || Status::unavailable("invalid Safe Browsing cache duration");
    let value = value.strip_suffix('s').ok_or_else(invalid)?;
    let (seconds, fraction) = value.split_once('.').unwrap_or((value, ""));
    if seconds.is_empty()
        || !seconds.bytes().all(|b| b.is_ascii_digit())
        || fraction.len() > 9
        || !fraction.bytes().all(|b| b.is_ascii_digit())
        || value.ends_with('.')
    {
        return Err(invalid());
    }
    let seconds = seconds.parse::<u64>().map_err(|_| invalid())?;
    let nanos = if fraction.is_empty() {
        0
    } else {
        fraction.parse::<u32>().map_err(|_| invalid())? * 10u32.pow(9 - fraction.len() as u32)
    };
    Ok(Duration::new(seconds, nanos))
}

fn request_url(target: &HttpRequestTarget) -> Result<String, Status> {
    let invalid = || Status::invalid_argument("unsupported or ambiguous HTTP request target");
    // CONNECT parsing supplies an unbracketed IPv6 host. Brackets belong to the
    // URL authority, not the supervisor's destination identity.
    let host = match target.host.parse::<std::net::Ipv6Addr>() {
        Ok(address) => format!("[{address}]"),
        Err(_) => target.host.clone(),
    };
    if !matches!(target.scheme.as_str(), "http" | "https")
        || !(1..=65535).contains(&target.port)
        || target.host.is_empty()
        || target
            .host
            .bytes()
            .any(|b| b <= 32 || b >= 127 || b"/@?#\\%".contains(&b))
        || (host.contains(':') && !(host.starts_with('[') && host.ends_with(']')))
        || !target.path.starts_with('/')
        || target.path.starts_with("//")
        || target.path.contains(['?', '#', '\\'])
        || target.query.contains('#')
    {
        return Err(invalid());
    }
    let mut raw = format!(
        "{}://{}:{}{}",
        target.scheme, host, target.port, target.path
    );
    if !target.query.is_empty() {
        raw.push('?');
        raw.push_str(&target.query);
    }
    if raw.len() > MAX_URL_BYTES || raw.bytes().any(|b| b < 32 || b == 127) {
        return Err(invalid());
    }
    let parsed = Url::parse(&raw).map_err(|_| invalid())?;
    // Do not silently check a target that the URL parser rewrote (dot segments,
    // whitespace, backslashes, or Unicode). The POC fails closed on these inputs.
    if parsed.host_str().is_none()
        || !parsed.username().is_empty()
        || parsed.password().is_some()
        || parsed.path() != target.path
        || parsed.query().unwrap_or("") != target.query
        || parsed.fragment().is_some()
    {
        return Err(invalid());
    }
    Ok(parsed.to_string())
}

fn validate_config(config: Option<&prost_types::Struct>) -> Result<(), &'static str> {
    if config.is_some_and(|config| !config.fields.is_empty()) {
        Err("this prototype accepts only an empty config; configure the API key on the service")
    } else {
        Ok(())
    }
}

#[tonic::async_trait]
impl SupervisorMiddleware for SafeBrowsing {
    type EvaluateWebSocketSessionStream = WebSocketResponseStream;

    async fn describe(
        &self,
        request: Request<MiddlewareDescribeRequest>,
    ) -> Result<Response<MiddlewareManifest>, Status> {
        use openshell_core::extension_protocol::{
            ExtensionFamily, extension_metadata, validate_gateway_metadata,
        };
        let extension = extension_metadata(
            ExtensionFamily::SupervisorMiddleware,
            MANIFEST_NAME,
            openshell_core::VERSION,
            [],
        );
        validate_gateway_metadata(
            ExtensionFamily::SupervisorMiddleware,
            MANIFEST_NAME,
            Some(&extension),
            request.into_inner().gateway,
        )
        .map_err(|_| Status::failed_precondition("incompatible gateway middleware protocol"))?;
        Ok(Response::new(MiddlewareManifest {
            name: MANIFEST_NAME.into(),
            service_version: env!("CARGO_PKG_VERSION").into(),
            bindings: vec![MiddlewareBinding {
                operation: SupervisorMiddlewareOperation::HttpRequest as i32,
                phase: SupervisorMiddlewarePhase::PreCredentials as i32,
                max_payload_bytes: MAX_PAYLOAD_BYTES,
                request_timeout: None,
            }],
            expected_audience: String::new(),
            extension: Some(extension),
        }))
    }

    async fn validate_config(
        &self,
        request: Request<ValidateConfigRequest>,
    ) -> Result<Response<ValidateConfigResponse>, Status> {
        let reason = validate_config(request.into_inner().config.as_ref())
            .err()
            .unwrap_or("");
        Ok(Response::new(ValidateConfigResponse {
            valid: reason.is_empty(),
            reason: reason.into(),
        }))
    }

    async fn evaluate_http_request(
        &self,
        request: Request<HttpRequestEvaluation>,
    ) -> Result<Response<HttpRequestResult>, Status> {
        let request = request.into_inner();
        if request.phase != SupervisorMiddlewarePhase::PreCredentials as i32 {
            return Err(Status::invalid_argument(
                "only PRE_CREDENTIALS is supported",
            ));
        }
        validate_config(request.config.as_ref()).map_err(Status::invalid_argument)?;
        let target = request
            .target
            .ok_or_else(|| Status::invalid_argument("HTTP target is required"))?;
        let url = request_url(&target)?;
        let unsafe_url = self.check(&url).await?;
        Ok(Response::new(if unsafe_url {
            HttpRequestResult {
                decision: Decision::Deny as i32,
                reason: "Potentially unsafe URL. Advisory provided by Google: https://safebrowsing.google.com/".into(),
                reason_code: "safe_browsing_threat".into(),
                findings: vec![Finding {
                    r#type: "safe_browsing.threat".into(), label: "Potentially unsafe URL; advisory provided by Google".into(),
                    count: 1, confidence: "medium".into(), severity: "high".into(),
                }], ..Default::default()
            }
        } else {
            HttpRequestResult {
                decision: Decision::Allow as i32,
                ..Default::default()
            }
        }))
    }

    async fn evaluate_web_socket_session(
        &self,
        _request: Request<tonic::Streaming<WebSocketSessionEvent>>,
    ) -> Result<Response<Self::EvaluateWebSocketSessionStream>, Status> {
        Err(Status::unimplemented(
            "WebSocket inspection is not supported",
        ))
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    let api_key = std::env::var("SAFE_BROWSING_API_KEY")
        .map_err(|_| "set SAFE_BROWSING_API_KEY on the middleware service process")?;
    let service = SafeBrowsing::new(
        cli.api_endpoint,
        &api_key,
        Duration::from_millis(cli.timeout_ms),
    )?;
    eprintln!(
        "Experimental Safe Browsing middleware listening on {} (plaintext, full URL lookups)",
        cli.bind
    );
    tonic::transport::Server::builder()
        .concurrency_limit_per_connection(64)
        .add_service(
            SupervisorMiddlewareServer::new(service)
                .max_decoding_message_size(MAX_PAYLOAD_BYTES as usize + 512 * 1024),
        )
        .serve_with_shutdown(cli.bind, async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
}

#[cfg(test)]
mod tests;
