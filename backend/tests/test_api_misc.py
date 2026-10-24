"""Health, error format, CORS, OpenAPI."""

from flask import Flask
from flask.testing import FlaskClient

from tests.conftest import make_app


def assert_error_shape(body: dict[str, object], code: str) -> None:
    assert set(body) == {"error", "message", "details"}
    assert body["error"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["details"], dict)


def test_health_checks_the_database(client: FlaskClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200 and res.get_json() == {"status": "ok"}


def test_health_reports_503_when_the_database_is_down() -> None:
    broken = make_app(DATABASE_URL="postgresql://postgres@127.0.0.1:1/nope")
    res = broken.test_client().get("/api/health")
    assert res.status_code == 503
    assert_error_shape(res.get_json(), "service_unavailable")


def test_404_405_and_unknown_api_paths_use_the_error_format(client: FlaskClient) -> None:
    assert_error_shape(client.get("/api/nope").get_json(), "not_found")
    assert client.get("/api/nope").status_code == 404
    res = client.delete("/api/health")
    assert res.status_code == 405
    assert_error_shape(res.get_json(), "method_not_allowed")
    res = client.get("/api/bookings/abc")
    assert res.status_code == 404
    assert_error_shape(res.get_json(), "not_found")
    assert client.get("/").status_code == 404


def test_unexpected_errors_become_a_json_500_without_leaking_details() -> None:
    fresh = make_app()

    @fresh.get("/api/_boom")
    def boom() -> str:
        raise RuntimeError("secret internal detail")

    res = fresh.test_client().get("/api/_boom")
    assert res.status_code == 500
    body = res.get_json()
    assert_error_shape(body, "internal_error")
    assert "secret" not in str(body)


def test_cors_allows_only_configured_origins(client: FlaskClient) -> None:
    ok = client.options(
        "/api/bookings",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,idempotency-key,content-type",
        },
    )
    assert ok.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    allowed = ok.headers["Access-Control-Allow-Headers"].lower()
    assert "idempotency-key" in allowed and "authorization" in allowed
    simple = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert simple.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    evil = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in evil.headers


def test_openapi_spec_and_docs_page(client: FlaskClient) -> None:
    spec = client.get("/api/openapi.json")
    assert spec.status_code == 200
    doc = spec.get_json()
    assert doc["openapi"].startswith("3.") and doc["info"]["title"] == "Hotel Medina API"
    docs = client.get("/api/docs")
    assert docs.status_code == 200 and "text/html" in docs.content_type
    assert "/api/openapi.json" in docs.get_data(as_text=True)


def test_every_api_route_is_documented_in_the_openapi_spec(app: Flask, client: FlaskClient) -> None:
    import re

    documented = {
        (path, method.upper())
        for path, ops in client.get("/api/openapi.json").get_json()["paths"].items()
        for method in ops
    }
    actual = set()
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/") or rule.rule in ("/api/docs", "/api/openapi.json"):
            continue
        path = re.sub(r"<(?:int:)?(\w+)>", r"{\1}", rule.rule)
        actual |= {(path, m) for m in rule.methods or () if m not in ("HEAD", "OPTIONS")}
    assert actual == documented


def test_debug_mode_is_never_on(app: Flask) -> None:
    assert app.debug is False
