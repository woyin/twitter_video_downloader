"""回归测试:锁定 extract_video_url 的格式化过滤与排序行为。

这些测试不访问网络,yt-dlp 由 FakeYDL 替代。
"""

import pytest
import yt_dlp

import main


class FakeYDL:
    """替代 yt_dlp.YoutubeDL,只实现本项目用到的接口。"""

    info = None
    error = None
    last_opts = None

    def __init__(self, opts=None):
        FakeYDL.last_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        if FakeYDL.error is not None:
            raise FakeYDL.error
        return FakeYDL.info


@pytest.fixture(autouse=True)
def fake_ytdlp(monkeypatch):
    FakeYDL.info = None
    FakeYDL.error = None
    FakeYDL.last_opts = None
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    main._CACHE.clear()
    yield FakeYDL


def fmt(**kw):
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


def test_picks_highest_height(fake_ytdlp):
    FakeYDL.info = {
        "formats": [
            fmt(format_id="low", height=360, width=640, url="https://a/360.mp4"),
            fmt(format_id="high", height=1080, width=1920, url="https://a/1080.mp4"),
            fmt(format_id="mid", height=720, url="https://a/720.mp4"),
        ]
    }
    result = main.extract_video_url("https://x.com/u/status/1")

    assert result["success"] is True
    assert result["video_url"] == "https://a/1080.mp4"
    assert [f["format_id"] for f in result["all_formats"]] == ["low", "mid", "high"]


def test_excludes_hls_streams(fake_ytdlp):
    FakeYDL.info = {
        "formats": [
            fmt(format_id="hls", url="https://a/playlist.m3u8", protocol="m3u8_native"),
            fmt(format_id="mp4", url="https://a/ok.mp4"),
        ]
    }
    result = main.extract_video_url("https://x.com/u/status/1")

    assert result["success"] is True
    assert [f["format_id"] for f in result["all_formats"]] == ["mp4"]
    assert result["video_url"] == "https://a/ok.mp4"


def test_excludes_formats_without_dimensions(fake_ytdlp):
    FakeYDL.info = {
        "formats": [
            fmt(format_id="audio", width=0, height=0, url="https://a/audio.mp4"),
            fmt(format_id="video", url="https://a/v.mp4"),
        ]
    }
    result = main.extract_video_url("https://x.com/u/status/1")

    assert [f["format_id"] for f in result["all_formats"]] == ["video"]


def test_all_formats_have_no_internal_sort_key(fake_ytdlp):
    FakeYDL.info = {"formats": [fmt()]}
    result = main.extract_video_url("https://x.com/u/status/1")

    for f in result["all_formats"]:
        assert "_height" not in f


def test_no_formats_returns_failure(fake_ytdlp):
    FakeYDL.info = {"formats": []}
    result = main.extract_video_url("https://x.com/u/status/1")

    assert result["success"] is False
    assert result["message"] == "本帖子中无视频可下载"


def test_info_none_returns_failure(fake_ytdlp):
    FakeYDL.info = None
    result = main.extract_video_url("https://x.com/u/status/1")

    assert result["success"] is False
    assert result["message"] == "本帖子中无视频可下载"


def test_video_unavailable_maps_to_friendly_message(fake_ytdlp):
    FakeYDL.error = yt_dlp.utils.DownloadError("ERROR: Video unavailable")
    result = main.extract_video_url("https://x.com/u/status/1")

    assert result["success"] is False
    assert result["message"] == "本帖子中无视频可下载"


def test_generic_error_does_not_leak_internals(fake_ytdlp):
    FakeYDL.error = yt_dlp.utils.DownloadError("ERROR: secret internal path /etc/passwd")
    result = main.extract_video_url("https://x.com/u/status/1")

    assert result["success"] is False
    assert "/etc/passwd" not in result["message"]


def test_ydl_opts_are_hardened(fake_ytdlp):
    FakeYDL.info = {"formats": [fmt()]}
    main.extract_video_url("https://x.com/u/status/1")

    opts = FakeYDL.last_opts
    assert opts["quiet"] is True
    assert opts["noplaylist"] is True
    assert opts["socket_timeout"] > 0
