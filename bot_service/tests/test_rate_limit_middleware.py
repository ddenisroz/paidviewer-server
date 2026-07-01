from starlette.requests import Request

from middleware.rate_limit_middleware import RateLimitMiddleware


def _build_request(headers=None, cookies=None):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/commands",
        "headers": headers or [],
        "client": ("172.18.0.5", 12345),
    }
    request = Request(scope)
    if cookies:
        request._cookies = cookies
    return request


def test_resolve_identifier_prefers_authenticated_session(monkeypatch):
    request = _build_request(cookies={"session_id": "sess-123"})

    monkeypatch.setattr(
        "middleware.rate_limit_middleware.get_session_data",
        lambda req: {"user_id": 42} if req is request else None,
    )

    identifier = RateLimitMiddleware._resolve_identifier(request)

    assert identifier == "user:42"


def test_resolve_identifier_falls_back_to_ip(monkeypatch):
    request = _build_request()

    monkeypatch.setattr("middleware.rate_limit_middleware.get_session_data", lambda req: None)

    identifier = RateLimitMiddleware._resolve_identifier(request)

    assert identifier == "ip:172.18.0.5"
