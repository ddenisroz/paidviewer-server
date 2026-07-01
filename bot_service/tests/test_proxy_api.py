import httpx

from api.proxy_api import TRANSPARENT_GIF


class _StubResponse:
    def __init__(self, status_code: int, *, url: str, headers: dict[str, str] | None = None, content: bytes = b"") -> None:
        self.status_code = status_code
        self.url = url
        self.headers = headers or {}
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", self.url)
            response = httpx.Response(
                self.status_code,
                request=request,
                headers=self.headers,
                content=self.content,
            )
            raise httpx.HTTPStatusError("upstream failure", request=request, response=response)


class _StubAsyncClient:
    def __init__(self, responses: list[_StubResponse], **_kwargs) -> None:
        self._responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *_args, **_kwargs):
        if not self._responses:
            raise AssertionError("No stub response configured")
        return self._responses.pop(0)


def test_proxy_7tv_returns_transparent_fallback_for_missing_image(client, monkeypatch):
    monkeypatch.setattr(
        "api.proxy_api.httpx.AsyncClient",
        lambda **kwargs: _StubAsyncClient(
            [
                _StubResponse(
                    404,
                    url="https://cdn.7tv.app/emote/missing/4x.webp",
                    headers={"Content-Type": "image/webp"},
                )
            ],
            **kwargs,
        ),
    )

    response = client.get("/api/proxy/7tv/cdn.7tv.app/emote/missing/4x.webp")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/gif")
    assert response.content == TRANSPARENT_GIF


def test_proxy_7tv_allows_relative_redirect_and_still_falls_back_for_dead_asset(client, monkeypatch):
    monkeypatch.setattr(
        "api.proxy_api.httpx.AsyncClient",
        lambda **kwargs: _StubAsyncClient(
            [
                _StubResponse(
                    302,
                    url="https://cdn.7tv.app/emote/stale/4x.webp",
                    headers={"Location": "/emote/final-dead/4x.webp"},
                ),
                _StubResponse(
                    404,
                    url="https://cdn.7tv.app/emote/final-dead/4x.webp",
                    headers={"Content-Type": "image/webp"},
                ),
            ],
            **kwargs,
        ),
    )

    response = client.get("/api/proxy/7tv/cdn.7tv.app/emote/stale/4x.webp")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/gif")
    assert response.content == TRANSPARENT_GIF


def test_proxy_7tv_returns_404_for_missing_metadata(client, monkeypatch):
    monkeypatch.setattr(
        "api.proxy_api.httpx.AsyncClient",
        lambda **kwargs: _StubAsyncClient(
            [
                _StubResponse(
                    404,
                    url="https://api.7tv.app/v3/emote-sets/missing",
                    headers={"Content-Type": "application/json"},
                    content=b'{"error":"missing"}',
                )
            ],
            **kwargs,
        ),
    )

    response = client.get("/api/proxy/7tv/api.7tv.app/v3/emote-sets/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Upstream resource was not found"
