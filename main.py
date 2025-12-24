"""
Twitter/X Video URL Extractor API

解析 Twitter/X 帖子中的视频真实 URL
"""

from typing import Optional

import yt_dlp

from fastapi import FastAPI, HTTPException, Query, Depends, Security
from fastapi.security.api_key import APIKeyHeader, APIKeyQuery
from starlette.status import HTTP_403_FORBIDDEN
import os

app = FastAPI(
    title="Twitter Video Downloader API",
    description="解析 Twitter/X 帖子中的视频真实下载地址",
    version="1.0.0",
)

# 获取环境变量中的 API KEY
API_KEY = os.getenv("API_KEY")
API_KEY_NAME = "x-api-key"

api_key_query = APIKeyQuery(name=API_KEY_NAME, auto_error=False)
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(
    api_key_query: str = Security(api_key_query),
    api_key_header: str = Security(api_key_header),
):
    # 如果没有设置 API_KEY 环境变量，则视为不需要鉴权
    if not API_KEY:
        return None

    if api_key_query == API_KEY:
        return api_key_query
    if api_key_header == API_KEY:
        return api_key_header
    
    raise HTTPException(
        status_code=HTTP_403_FORBIDDEN, detail="Could not validate credentials"
    )

class ExtractRequest(BaseModel):
    """POST 请求体"""

    xid: str


class VideoFormat(BaseModel):
    """视频格式信息"""

    format_id: str
    url: str
    ext: str
    resolution: Optional[str] = None
    filesize: Optional[int] = None


class ExtractResponse(BaseModel):
    """成功响应"""

    success: bool = True
    video_url: str
    all_formats: list[VideoFormat] = []


class ErrorResponse(BaseModel):
    """错误响应"""

    success: bool = False
    message: str


def extract_video_url(url: str) -> dict:
    """
    使用 yt-dlp 提取视频 URL

    Args:
        url: Twitter/X 帖子 URL

    Returns:
        包含视频 URL 的字典，或错误信息
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if info is None:
                return {"success": False, "message": "本帖子中无视频可下载"}

            # 过滤出可直接下载的 mp4 格式（排除 m3u8 HLS 流）
            formats = info.get("formats", [])
            video_formats = []
            for f in formats:
                video_url = f.get("url", "")
                ext = f.get("ext", "")
                protocol = f.get("protocol", "")
                height = f.get("height", 0) or 0
                width = f.get("width", 0) or 0

                # 只要可直接下载的 mp4，排除 m3u8/HLS 流
                # Twitter 的直链 mp4 格式的 vcodec 可能是 None，但有 width/height
                is_direct_mp4 = (
                    video_url
                    and protocol in ("https", "http")
                    and ".m3u8" not in video_url
                    and (width > 0 or height > 0)  # 必须有尺寸信息
                )

                if is_direct_mp4:
                    video_formats.append(
                        {
                            "format_id": f.get("format_id", ""),
                            "url": video_url,
                            "ext": ext,
                            "resolution": f.get("resolution", f"{width}x{height}"),
                            "filesize": f.get("filesize"),
                            "_height": height,  # 用于排序
                        }
                    )

            if not video_formats:
                return {"success": False, "message": "本帖子中无视频可下载"}

            # 按高度排序，获取最高画质
            video_formats.sort(key=lambda x: x.get("_height", 0))

            # 移除内部排序字段
            for vf in video_formats:
                vf.pop("_height", None)

            # 最高画质的视频 URL
            best_url = video_formats[-1]["url"]

            return {
                "success": True,
                "video_url": best_url,
                "all_formats": video_formats,
            }

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "Video unavailable" in error_msg or "not a video" in error_msg.lower():
            return {"success": False, "message": "本帖子中无视频可下载"}
        return {"success": False, "message": f"解析失败: {error_msg}"}
    except Exception as e:
        return {"success": False, "message": f"解析失败: {str(e)}"}


@app.get(
    "/extract",
    response_model=ExtractResponse | ErrorResponse,
    summary="提取视频 URL (GET)",
    description="通过 GET 请求提取 Twitter/X 帖子中的视频 URL",
)
async def extract_video_get(
    xid: str = Query(..., description="Twitter/X 帖子 URL"),
    api_key: str = Depends(get_api_key),
):
    """
    GET 方法提取视频 URL

    - **xid**: Twitter/X 帖子 URL (如: https://x.com/user/status/123456)
    - **x-api-key**: 在Header或Query参数中携带 API KEY
    """
    result = extract_video_url(xid)
    return result


@app.post(
    "/extract",
    response_model=ExtractResponse | ErrorResponse,
    summary="提取视频 URL (POST)",
    description="通过 POST 请求提取 Twitter/X 帖子中的视频 URL",
)
async def extract_video_post(
    request: ExtractRequest,
    api_key: str = Depends(get_api_key)
):
    """
    POST 方法提取视频 URL

    请求体:
    - **xid**: Twitter/X 帖子 URL (如: https://x.com/user/status/123456)
    - **x-api-key**: 在Header或Query参数中携带 API KEY
    """
    result = extract_video_url(request.xid)
    return result


@app.get("/", summary="健康检查")
async def root():
    """API 健康检查端点"""
    return {"status": "ok", "message": "Twitter Video Downloader API is running"}
