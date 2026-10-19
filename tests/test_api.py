"""HTTP 层回归测试:鉴权、URL 白名单、缓存与路由契约。"""

import yt_dlp
from fastapi.testclient import TestClient

import main

GOOD_URL = "https://x.com/SpaceX/status/1871329241904255193"


class FakeYDL:
    info = None
    calls = 0

    def __init__(self, opts=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        FakeYDL.calls += 1
        return FakeYDL.info


def _fmt(**kw):
    base = {
        "format_id": "f",
        "url": "https://video.twimg.com/x.mp4",
        "ext": "mp4",
        "protocol": "https",
        "width": 1280,
        "height": 720,
    }
    base.update(kw)
    return base


def setup_function():
    FakeYDL.info = {"formats": [_fmt()]}
    FakeYDL.calls = 0
    main._CACHE.clear()


def _client(monkeypatch, api_key="secret-key"):
    if api_key is None:
        monkeypatch.delenv("API_KEY", raising=False)
    else:
        monkeypatch.setenv("API_KEY", api_key)
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    return TestClient(main.app)


def test_health_is_public(monkeypatch):
    client = _client(monkeypatch)
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_missing_api_key_rejects_all_requests(monkeypatch):
    client = _client(monkeypatch, api_key=None)
    resp = client.get("/extract", params={"xid": GOOD_URL})
    assert resp.status_code == 503


def test_wrong_key_is_forbidden(monkeypatch):
    client = _client(monkeypatch)
    resp = client.get("/extract", params={"xid": GOOD_URL, "x-api-key": "nope"})
    assert resp.status_code == 403
    assert FakeYDL.calls == 0


def test_header_key_accepted(monkeypatch):
    client = _client(monkeypatch)
    resp = client.get("/extract", params={"xid": GOOD_URL}, headers={"x-api-key": "secret-key"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_query_key_accepted(monkeypatch):
    client = _client(monkeypatch)
    resp = client.get("/extract", params={"xid": GOOD_URL, "x-api-key": "secret-key"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_post_extract_works(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/extract", json={"xid": GOOD_URL}, headers={"x-api-key": "secret-key"})
    assert resp.status_code == 200
    assert resp.json()["video_url"] == "https://video.twimg.com/x.mp4"


def test_non_twitter_host_is_rejected_without_network(monkeypatch):
    client = _client(monkeypatch)
    resp = client.get(
        "/extract",
        params={"xid": "https://evil.example.com/status/1", "x-api-key": "secret-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == main.INVALID_URL_MESSAGE
    assert FakeYDL.calls == 0


def test_cache_avoids_second_extraction(monkeypatch):
    client = _client(monkeypatch)
    for _ in range(3):
        resp = client.get("/extract", params={"xid": GOOD_URL, "x-api-key": "secret-key"})
        assert resp.status_code == 200
    assert FakeYDL.calls == 1


def test_cache_is_keyed_by_url(monkeypatch):
    client = _client(monkeypatch)
    other = "https://twitter.com/other/status/999"
    client.get("/extract", params={"xid": GOOD_URL, "x-api-key": "secret-key"})
    client.get("/extract", params={"xid": other, "x-api-key": "secret-key"})
    assert FakeYDL.calls == 2


def test_failure_is_not_cached(monkeypatch):
    client = _client(monkeypatch)
    FakeYDL.info = {"formats": []}
    for _ in range(2):
        resp = client.get("/extract", params={"xid": GOOD_URL, "x-api-key": "secret-key"})
        assert resp.json()["success"] is False
    assert FakeYDL.calls == 2


def test_routes_are_sync_functions():
    """阻塞的 yt-dlp 调用必须运行在线程池中,不能占用事件循环。"""
    import inspect

    assert not inspect.iscoroutinefunction(main.extract_video_get)
    assert not inspect.iscoroutinefunction(main.extract_video_post)
    assert inspect.iscoroutinefunction(main.get_api_key)
