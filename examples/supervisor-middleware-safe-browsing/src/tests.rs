// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

use super::*;
use openshell_core::proto::HttpRequestTarget;
use wiremock::{
    Mock, MockServer, ResponseTemplate,
    matchers::{header, method, path, query_param},
};

fn target(path: &str) -> HttpRequestTarget {
    HttpRequestTarget {
        scheme: "https".into(),
        host: "example.com".into(),
        port: 443,
        method: "GET".into(),
        path: path.into(),
        query: String::new(),
    }
}

#[test]
fn preserves_query_encoding_and_nonstandard_port() {
    let mut target = target("/a%2Fb");
    target.port = 8443;
    target.query = "a=1&a=2&token=x%2By".into();
    assert_eq!(
        request_url(&target).unwrap(),
        "https://example.com:8443/a%2Fb?a=1&a=2&token=x%2By"
    );
}

#[test]
fn rejects_authority_or_fragment_smuggling() {
    for host in [
        "example.com@evil.test",
        "example.com/path",
        "example.com?query",
        "example.com#frag",
        "example.com\\evil",
        "",
    ] {
        let mut input = target("/");
        input.host = host.into();
        assert!(request_url(&input).is_err(), "host: {host}");
    }
    for path in [
        "//evil.test/x",
        "http://evil.test/x",
        "/x#hidden",
        "/x?query",
        "/x\\y",
        "relative",
        "/a/../b",
        "/%2e%2e/b",
    ] {
        assert!(request_url(&target(path)).is_err(), "path: {path}");
    }
    let mut input = target("/");
    input.query = "a=b#hidden".into();
    assert!(request_url(&input).is_err());
}

#[test]
fn permits_ipv6_and_rejects_non_http_targets() {
    let mut input = target("/");
    input.host = "[2001:db8::1]".into();
    assert_eq!(request_url(&input).unwrap(), "https://[2001:db8::1]/");
    input.scheme = "wss".into();
    assert!(request_url(&input).is_err());
    input.scheme = "https".into();
    input.port = 0;
    assert!(request_url(&input).is_err());
}

#[test]
fn parses_only_nonnegative_protobuf_durations() {
    assert_eq!(cache_duration("3.000000001s").unwrap(), Duration::new(3, 1));
    assert_eq!(cache_duration("0s").unwrap(), Duration::ZERO);
    for invalid in [
        "",
        "1",
        "-1s",
        "NaNs",
        "infs",
        "1.s",
        "1.0000000001s",
        "1e3s",
    ] {
        assert!(cache_duration(invalid).is_err(), "{invalid}");
    }
}

async fn checker(server: &MockServer) -> SafeBrowsing {
    SafeBrowsing::new(
        format!("{}/v5/urls:search", server.uri()),
        "test-api-key",
        Duration::from_secs(1),
    )
    .unwrap()
}

async fn response(server: &MockServer, template: ResponseTemplate, count: u64) {
    Mock::given(method("GET"))
        .and(path("/v5/urls:search"))
        .and(header("x-goog-api-key", "test-api-key"))
        .and(query_param("urls", "https://example.com/a?x=1&x=2"))
        .respond_with(template)
        .expect(count)
        .mount(server)
        .await;
}

const LOOKUP: &str = "https://example.com/a?x=1&x=2";

#[tokio::test]
async fn clean_verdict_is_cached() {
    let server = MockServer::start().await;
    response(
        &server,
        ResponseTemplate::new(200).set_body_json(serde_json::json!({"cacheDuration":"300s"})),
        1,
    )
    .await;
    let checker = checker(&server).await;
    assert!(!checker.check(LOOKUP).await.unwrap());
    assert!(!checker.check(LOOKUP).await.unwrap());
    server.verify().await;
}

#[tokio::test]
async fn matching_parent_expression_is_denied_and_cached() {
    let server = MockServer::start().await;
    response(&server, ResponseTemplate::new(200).set_body_json(serde_json::json!({
        "cacheDuration":"300s", "threats":[{"url":"https://example.com/", "threatTypes":["MALWARE"]}]
    })), 1).await;
    let checker = checker(&server).await;
    assert!(checker.check(LOOKUP).await.unwrap());
    assert!(checker.check(LOOKUP).await.unwrap());
    server.verify().await;
}

#[tokio::test]
async fn expired_verdict_is_checked_again() {
    let server = MockServer::start().await;
    response(
        &server,
        ResponseTemplate::new(200).set_body_json(serde_json::json!({"cacheDuration":"0s"})),
        2,
    )
    .await;
    let checker = checker(&server).await;
    assert!(!checker.check(LOOKUP).await.unwrap());
    assert!(!checker.check(LOOKUP).await.unwrap());
    server.verify().await;
}

#[tokio::test]
async fn errors_are_not_cached_or_returned_with_secrets() {
    for template in [
        ResponseTemplate::new(429).set_body_string("test-api-key"),
        ResponseTemplate::new(503),
        ResponseTemplate::new(200).set_body_string("not JSON test-api-key"),
        ResponseTemplate::new(200).set_body_json(serde_json::json!({})),
        ResponseTemplate::new(200).set_body_json(serde_json::json!({"cacheDuration":"-1s"})),
        ResponseTemplate::new(200)
            .set_body_json(serde_json::json!({"cacheDuration":"1s", "threats":[{}]})),
        ResponseTemplate::new(200).set_body_string("x".repeat(MAX_RESPONSE_BYTES + 1)),
    ] {
        let server = MockServer::start().await;
        response(&server, template, 2).await;
        let checker = checker(&server).await;
        for _ in 0..2 {
            let error = checker.check(LOOKUP).await.unwrap_err().to_string();
            assert!(!error.contains("test-api-key"));
            assert!(!error.contains("example.com"));
        }
        server.verify().await;
    }
}

#[tokio::test]
async fn timeout_is_a_failure() {
    let server = MockServer::start().await;
    response(
        &server,
        ResponseTemplate::new(200)
            .set_delay(Duration::from_millis(100))
            .set_body_json(serde_json::json!({"cacheDuration":"300s"})),
        1,
    )
    .await;
    let checker = SafeBrowsing::new(
        format!("{}/v5/urls:search", server.uri()),
        "test-api-key",
        Duration::from_millis(10),
    )
    .unwrap();
    assert!(checker.check(LOOKUP).await.is_err());
}

#[tokio::test]
async fn does_not_follow_api_redirects() {
    let destination = MockServer::start().await;
    let server = MockServer::start().await;
    response(
        &server,
        ResponseTemplate::new(302).insert_header("location", destination.uri()),
        1,
    )
    .await;
    assert!(checker(&server).await.check(LOOKUP).await.is_err());
    assert!(destination.received_requests().await.unwrap().is_empty());
}

#[test]
fn example_policy_is_valid() {
    let policy = openshell_policy::parse_sandbox_policy(include_str!("../policy.yaml")).unwrap();
    openshell_policy::validate_sandbox_policy(&policy).unwrap();
    assert_eq!(
        policy.network_middlewares["website-reputation"].on_error,
        "fail_closed"
    );
}

#[test]
fn endpoint_and_key_validation() {
    for endpoint in [
        "http://remote.example/v5/urls:search",
        "file:///tmp/lookup",
        "https://user:pass@example.com/",
        "https://example.com/?key=secret",
        "https://example.com/#fragment",
    ] {
        assert!(
            SafeBrowsing::new(endpoint.into(), "test", Duration::from_secs(1)).is_err(),
            "{endpoint}"
        );
    }
    for key in ["", "  ", "key\nvalue"] {
        assert!(SafeBrowsing::new(API_ENDPOINT.into(), key, Duration::from_secs(1)).is_err());
    }
}

#[tokio::test]
async fn stale_allow_is_not_reused() {
    let server = MockServer::start().await;
    response(&server, ResponseTemplate::new(200).set_body_json(serde_json::json!({
        "cacheDuration":"300s", "threats":[{"url":"https://example.com/", "threatTypes":["SOCIAL_ENGINEERING"]}]
    })), 1).await;
    let checker = checker(&server).await;
    checker.cache.lock().await.insert(
        LOOKUP.into(),
        CacheEntry {
            unsafe_url: false,
            expires: Instant::now() - Duration::from_secs(1),
        },
    );
    assert!(checker.check(LOOKUP).await.unwrap());
}

#[tokio::test]
async fn cache_is_bounded() {
    let server = MockServer::start().await;
    response(
        &server,
        ResponseTemplate::new(200).set_body_json(serde_json::json!({"cacheDuration":"300s"})),
        1,
    )
    .await;
    let checker = checker(&server).await;
    for i in 0..MAX_CACHE_ENTRIES {
        checker.cache.lock().await.insert(
            format!("https://example.com/{i}"),
            CacheEntry {
                unsafe_url: false,
                expires: Instant::now() + Duration::from_secs(300),
            },
        );
    }
    assert!(!checker.check(LOOKUP).await.unwrap());
    assert!(checker.cache.lock().await.len() <= MAX_CACHE_ENTRIES);
}

#[tokio::test]
async fn unknown_policy_config_is_rejected() {
    let server = MockServer::start().await;
    let checker = checker(&server).await;
    let config = prost_types::Struct {
        fields: [(
            "api_key".into(),
            prost_types::Value {
                kind: Some(prost_types::value::Kind::StringValue(
                    "do-not-put-secrets-in-policy".into(),
                )),
            },
        )]
        .into(),
    };
    let result = SupervisorMiddleware::validate_config(
        &checker,
        Request::new(ValidateConfigRequest {
            config: Some(config),
            ..Default::default()
        }),
    )
    .await
    .unwrap()
    .into_inner();
    assert!(!result.valid);
    assert!(server.received_requests().await.unwrap().is_empty());
}

#[tokio::test]
async fn grpc_service_blocks_threats_and_fails_closed_on_outage() {
    use openshell_core::proto::{
        SupervisorMiddlewareBinding, SupervisorMiddlewareBindingPolicy, SupervisorMiddlewareService,
    };
    use openshell_supervisor_middleware::{
        ChainEntry, ChainRunner, HttpRequestInput, MiddlewareRegistry, OnError,
    };
    use tokio_stream::wrappers::TcpListenerStream;
    let google = MockServer::start().await;
    let service = checker(&google).await;
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let (shutdown_tx, shutdown_rx) = tokio::sync::oneshot::channel();
    let task = tokio::spawn(
        tonic::transport::Server::builder()
            .add_service(SupervisorMiddlewareServer::new(service))
            .serve_with_incoming_shutdown(TcpListenerStream::new(listener), async {
                let _ = shutdown_rx.await;
            }),
    );
    let registry = MiddlewareRegistry::connect_services(
        Vec::new(),
        vec![SupervisorMiddlewareService {
            name: "safe-browsing-example".into(),
            grpc_endpoint: format!("http://{address}"),
            max_payload_bytes: MAX_PAYLOAD_BYTES,
            allow_insecure_transport: true,
            request_timeout: Some(prost_types::Duration {
                seconds: 3,
                nanos: 0,
            }),
            binding_policy: SupervisorMiddlewareBindingPolicy::Exact as i32,
            bindings: vec![SupervisorMiddlewareBinding::HttpRequestPreCredentials as i32],
            ..Default::default()
        }],
    )
    .await
    .unwrap();
    let runner = ChainRunner::from_registry(registry);
    let chain = [ChainEntry {
        name: "website-reputation".into(),
        implementation: "safe-browsing-example".into(),
        order: 10,
        config: prost_types::Struct::default(),
        on_error: OnError::FailClosed,
    }];
    let input = || HttpRequestInput {
        request_id: "test".into(),
        sandbox_id: "sandbox".into(),
        sandbox_name: "sandbox".into(),
        workspace: "wrks-default".into(),
        scheme: "https".into(),
        host: "example.com".into(),
        port: 443,
        method: "GET".into(),
        path: "/a".into(),
        query: "x=1&x=2".into(),
        headers: vec![],
        connection_nominated_headers: vec![],
        body: vec![],
    };
    response(
        &google,
        ResponseTemplate::new(200).set_body_json(serde_json::json!({"cacheDuration":"0s"})),
        1,
    )
    .await;
    let allowed = runner.evaluate(&chain, input()).await.unwrap();
    assert!(allowed.allowed);
    assert!(!allowed.applied[0].failed);
    google.verify().await;
    google.reset().await;

    response(&google, ResponseTemplate::new(200).set_body_json(serde_json::json!({
        "cacheDuration":"0s", "threats":[{"url":"https://example.com/", "threatTypes":["MALWARE"]}]
    })), 1).await;
    let denied = runner.evaluate(&chain, input()).await.unwrap();
    assert!(!denied.allowed);
    assert_eq!(
        denied.denial.unwrap().reason_code.as_deref(),
        Some("safe_browsing_threat")
    );
    assert!(!denied.applied[0].failed);
    assert!(!denied.findings.is_empty());
    google.verify().await;
    google.reset().await;

    response(&google, ResponseTemplate::new(503), 1).await;
    let failed = runner.evaluate(&chain, input()).await.unwrap();
    assert!(!failed.allowed);
    assert!(failed.applied[0].failed);
    assert!(failed.denial.is_none());
    google.verify().await;
    drop(runner);
    shutdown_tx.send(()).unwrap();
    task.await.unwrap().unwrap();
}

#[test]
fn accepts_supervisor_bare_ipv6_host() {
    let mut input = target("/");
    input.host = "2001:db8::1".into();
    assert_eq!(request_url(&input).unwrap(), "https://[2001:db8::1]/");
}
