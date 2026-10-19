"""
Twitter/X Video URL Extractor API

解析 Twitter/X 帖子中的视频真实 URL,只返回可直接下载的 mp4 直链。
"""

from __future__ import annotations

import copy
import logging
import os
import secrets
import threading
import time
from collections import OrderedDict
from typing import Any
from urllib.parse import urlparse

import yt_dlp
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security.api_key import APIKeyHeader, APIKeyQuery
from pydantic import BaseModel, Field
from starlette.status import HTTP_403_FORBIDDEN, HTTP_503_SERVICE_UNAVAILABLE

logger = logging.getLogger("twitter_video_downloader")

API_KEY_ENV = "API_KEY"
API_KEY_NAME = "x-api-key"

# 允许解析的域名白名单,防止该接口被用作任意 URL 的 SSRF 跳板。
ALLOWED_HOSTS = frozenset(
    {
        "x.com",
        "www.x.com",
        "mobile.x.com",
        "twitter.com",
        "www.twitter.com",
        "mobile.twitter.com",
    }
)

# 可直接下载的协议;m3u8/HLS 需要播放器,不在本服务输出范围内。
DIRECT_PROTOCOLS = frozenset({"https", "http"})

CACHE_TTL_SECONDS = float(os.getenv("CACHE_TTL_SECONDS", "300"))
CACHE_MAX_ENTRIES = int(os.getenv("CACHE_MAX_ENTRIES", "256"))
SOCKET_TIMEOUT_SECONDS = float(os.getenv("YTDLP_SOCKET_TIMEOUT", "15"))
MAX_CONCURRENT_EXTRACTIONS = int(os.getenv("MAX_CONCURRENT_EXTRACTIONS", "8"))
QUEUE_WAIT_SECONDS = float(os.getenv("EXTRACT_QUEUE_WAIT_SECONDS", "20"))

NO_VIDEO_MESSAGE = "本帖子中无视频可下载"
INVALID_URL_MESSAGE = "无效的 Twitter/X 帖子链接"
BUSY_MESSAGE = "服务繁忙,请稍后重试"

app = FastAPI(
    title="Twitter Video Downloader API",
    description="解析 Twitter/X 帖子中的视频真实下载地址",
    version="1.1.0",
)

api_key_query = APIKeyQuery(name=API_KEY_NAME, auto_error=False)
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


class _TTLCache:
    """带过期时间与容量上限的线程安全缓存。"""

    def __init__(self, ttl_seconds: float, max_entries: int) -> None:
        self._ttl = ttl_seconds
        self._max = max(1, max_entries)
        self._lock = threading.Lock()
        self._data: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()

    @property
    def enabled(self) -> bool:
        return self._ttl > 0

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= now:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return copy.deepcopy(value)

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._data[key] = (time.monotonic() + self._ttl, copy.deepcopy(value))
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_CACHE = _TTLCache(CACHE_TTL_SECONDS, CACHE_MAX_ENTRIES)
_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_EXTRACTIONS)


class ExtractRequest(BaseModel):
    """POST 请求体"""

    xid: str


class VideoFormat(BaseModel):
    """视频格式信息"""

    format_id: str
    url: str
    ext: str
    resolution: str | None = None
    filesize: int | None = None


class ExtractResponse(BaseModel):
    """成功响应"""

    success: bool = True
    video_url: str
    all_formats: list[VideoFormat] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """错误响应"""

    success: bool = False
    message: str


def _configured_api_key() -> str | None:
    """读取当前进程的 API_KEY。空值视为未配置。"""
    return os.getenv(API_KEY_ENV) or None


async def get_api_key(
    api_key_query: str = Security(api_key_query),
    api_key_header: str = Security(api_key_header),
) -> str:
    """校验调用方凭据。

    未配置 API_KEY 时拒绝服务(fail-closed),而不是静默放行。
    使用常量时间比较,避免通过响应时间推断密钥。
    """
    expected = _configured_api_key()
    if expected is None:
        logger.error("拒绝请求:未设置 %s 环境变量", API_KEY_ENV)
        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务未配置 API_KEY,已拒绝所有请求",
        )

    provided = api_key_header or api_key_query
    if provided and secrets.compare_digest(provided, expected):
        return provided

    raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Could not validate credentials")


def _normalize_url(raw: str) -> str | None:
    """校验并规范化帖子 URL。非白名单域名返回 None。"""
    try:
        parsed = urlparse(raw.strip())
    except (ValueError, AttributeError):
        return None

    if parsed.scheme not in DIRECT_PROTOCOLS:
        return None
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        return None
    return parsed.geturl()


def _build_ydl_options() -> dict[str, Any]:
    """yt-dlp 选项。只做元数据解析,不下载媒体。"""
    return {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "noplaylist": True,
        "socket_timeout": SOCKET_TIMEOUT_SECONDS,
        "retries": 2,
        "extractor_retries": 1,
    }


def _collect_direct_formats(formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """筛选可直接下载的 mp4,按高度升序排列。"""
    collected: list[dict[str, Any]] = []
    for fmt in formats:
        url = fmt.get("url") or ""
        protocol = fmt.get("protocol") or ""
        height = fmt.get("height") or 0
        width = fmt.get("width") or 0

        # Twitter 直链 mp4 的 vcodec 可能为空,因此以尺寸信息作为判据。
        is_direct = (
            bool(url)
            and protocol in DIRECT_PROTOCOLS
            and ".m3u8" not in url
            and (width > 0 or height > 0)
        )
        if not is_direct:
            continue

        collected.append(
            {
                "format_id": fmt.get("format_id") or "",
                "url": url,
                "ext": fmt.get("ext") or "",
                "resolution": fmt.get("resolution") or f"{width}x{height}",
                "filesize": fmt.get("filesize"),
                "_height": height,
            }
        )

    collected.sort(key=lambda item: item["_height"])
    for item in collected:
        item.pop("_height", None)
    return collected


def _extract_uncached(url: str) -> dict[str, Any]:
    """执行一次真实的 yt-dlp 解析。异常在此收敛为通用错误信息。"""
    try:
        with yt_dlp.YoutubeDL(_build_ydl_options()) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        message = str(exc).lower()
        if "video unavailable" in message or "not a video" in message:
            return {"success": False, "message": NO_VIDEO_MESSAGE}
        logger.warning("yt-dlp 解析失败 url=%s: %s", url, exc)
        return {"success": False, "message": "解析失败,请确认链接有效且帖子包含视频"}
    except Exception:
        logger.exception("解析 %s 时发生未预期异常", url)
        return {"success": False, "message": "解析失败,请稍后重试"}

    if not info:
        return {"success": False, "message": NO_VIDEO_MESSAGE}

    formats = _collect_direct_formats(info.get("formats") or [])
    if not formats:
        return {"success": False, "message": NO_VIDEO_MESSAGE}

    return {
        "success": True,
        "video_url": formats[-1]["url"],
        "all_formats": formats,
    }


def extract_video_url(url: str) -> dict[str, Any]:
    """解析 Twitter/X 帖子并返回最高画质的直链 mp4。

    结果按 URL 做 TTL 缓存;并发解析数量由信号量限制。
    """
    normalized = _normalize_url(url)
    if normalized is None:
        return {"success": False, "message": INVALID_URL_MESSAGE}

    cached = _CACHE.get(normalized)
    if cached is not None:
        return cached

    if not _SEMAPHORE.acquire(timeout=QUEUE_WAIT_SECONDS):
        logger.warning("解析队列已满,拒绝 url=%s", normalized)
        return {"success": False, "message": BUSY_MESSAGE}

    try:
        result = _extract_uncached(normalized)
    finally:
        _SEMAPHORE.release()

    if result.get("success"):
        _CACHE.set(normalized, result)
    return result


@app.get(
    "/extract",
    response_model=ExtractResponse | ErrorResponse,
    summary="提取视频 URL (GET)",
    description="通过 GET 请求提取 Twitter/X 帖子中的视频 URL",
)
def extract_video_get(
    xid: str = Query(..., description="Twitter/X 帖子 URL"),
    api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """GET 方法提取视频 URL。

    - **xid**: Twitter/X 帖子 URL (如: https://x.com/user/status/123456)
    - **x-api-key**: 在 Header 或 Query 参数中携带 API KEY
    """
    return extract_video_url(xid)


@app.post(
    "/extract",
    response_model=ExtractResponse | ErrorResponse,
    summary="提取视频 URL (POST)",
    description="通过 POST 请求提取 Twitter/X 帖子中的视频 URL",
)
def extract_video_post(
    request: ExtractRequest,
    api_key: str = Depends(get_api_key),
) -> dict[str, Any]:
    """POST 方法提取视频 URL。

    请求体:
    - **xid**: Twitter/X 帖子 URL (如: https://x.com/user/status/123456)
    - **x-api-key**: 在 Header 中携带 API KEY
    """
    return extract_video_url(request.xid)


@app.get("/", summary="健康检查")
def root() -> dict[str, str]:
    """API 健康检查端点"""
    return {"status": "ok", "message": "Twitter Video Downloader API is running"}
