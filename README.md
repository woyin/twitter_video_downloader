# Twitter/X Video Downloader API

这是一个简单、轻量级的 API 服务，用于解析 Twitter (X) 帖子中的视频真实下载地址。它基于强大的 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 库构建，并封装为 Docker 镜像，方便快速部署。

## 特性

*   🚀 **开箱即用**: 提供 Docker 镜像，一键部署。
*   🎥 **智能解析**: 自动过滤 M3U8 流，直接提取最高画质的 MP4 直链。
*   🔒 **强制鉴权**: 必须设置 `API_KEY`，未设置时服务拒绝所有请求（fail-closed）。
*   🛡️ **域名白名单**: 只解析 x.com / twitter.com 链接，避免被当作任意 URL 代理。
*   ⚡ **高性能**: 解析结果按 URL 缓存，并发解析数受限，阻塞调用不占用事件循环。

## 快速开始

### 使用 Docker Compose (推荐)

1.  创建一个 `docker-compose.yml` 文件：

```yaml
version: '3.8'

services:
  twitter-downloader:
    image: ghcr.io/woyin/twitter_video_downloader:latest
    container_name: twitter_downloader
    restart: always
    ports:
      - "8000:8000"
    environment:
      - TZ=Asia/Shanghai
      # 必填:鉴权密钥,需与 iOS 快捷指令里填的 key 一致。不设则服务拒绝所有请求。
      - API_KEY=your_secret_key
      # 可选：修改容器内部监听端口 (默认 8000)
      - PORT=8000
```

2.  启动服务：

```bash
docker-compose up -d
```

### 直接运行 Docker

```bash
docker run -d \
  --name twitter_downloader \
  -p 8000:8000 \
  -e API_KEY=your_secret_key \
  ghcr.io/woyin/twitter_video_downloader:latest
```

## API 文档

API 启动后，可以访问 `http://localhost:8000/docs` 查看交互式 Swagger 文档。

### 提取视频 (GET)

**端点**: `/extract`

**参数**:
*   `xid`: Twitter/X 帖子 URL (例如 `https://x.com/user/status/123456`)，仅支持 x.com / twitter.com
*   `x-api-key`: 鉴权密钥，必填

**示例**:
```bash
curl "http://localhost:8000/extract?xid=https://x.com/SpaceX/status/1871329241904255193&x-api-key=your_secret_key"
```

### 提取视频 (POST)

**端点**: `/extract`

**Header**:
*   `x-api-key`: 鉴权密钥，必填

**Body**:
```json
{
  "xid": "https://x.com/SpaceX/status/1871329241904255193"
}
```

**响应**:
```json
{
  "success": true,
  "video_url": "https://video.twimg.com/...",
  "all_formats": [
    {
      "format_id": "api-video-0",
      "url": "https://video.twimg.com/...",
      "ext": "mp4",
      "resolution": "1280x720",
      "filesize": 1024000
    }
  ]
}
```

## iOS 快捷指令(一键存相册)

仓库 `shortcut/` 目录提供了一个 iOS 快捷指令,调用本服务的 `/extract` 接口,把视频推文**一键解析并存进 iPhone 相册**(支持分享菜单触发 + 手动粘贴兜底)。

详见 [`shortcut/README.md`](shortcut/README.md)。

## 错误响应

| HTTP 状态 | 场景 |
| :-- | :-- |
| `200` + `success: false` | 链接无效、帖子无视频、解析失败、服务繁忙 |
| `403` | API Key 缺失或不匹配 |
| `503` | 服务端未配置 `API_KEY` |

错误响应只返回通用提示，不暴露 yt-dlp 内部错误文本；详细原因写入服务端日志。

## 配置

| 环境变量 | 默认值 | 说明 |
| :-- | :-- | :-- |
| `API_KEY` | 无（必填） | 鉴权密钥 |
| `PORT` | `8000` | 容器内监听端口 |
| `WEB_CONCURRENCY` | `1` | uvicorn worker 进程数 |
| `CACHE_TTL_SECONDS` | `300` | 解析结果缓存秒数，`0` 关闭 |
| `CACHE_MAX_ENTRIES` | `256` | 缓存条目上限 |
| `YTDLP_SOCKET_TIMEOUT` | `15` | yt-dlp 网络超时秒数 |
| `MAX_CONCURRENT_EXTRACTIONS` | `8` | 同时解析数上限 |
| `EXTRACT_QUEUE_WAIT_SECONDS` | `20` | 排队超时，超时返回"服务繁忙" |

## 开发

本项目使用 [uv](https://docs.astral.sh/uv/) 进行 Python 版本与依赖管理。

1.  克隆仓库
2.  安装依赖(自动创建 `.venv`、按 `uv.lock` 锁定版本): `uv sync`
3.  本地运行: `uv run uvicorn main:app --reload`
4.  更新依赖后重新锁定: `uv lock`

### 测试与静态检查

```bash
uv run pytest -q          # 单元测试（不联网，yt-dlp 被替身替换）
uv run ruff check .       # 静态检查
uv run ruff format .      # 格式化
```

CI 在每次 push 和 PR 上运行 ruff 与 pytest（`.github/workflows/test.yml`），Docker 镜像发布由 `publish.yml` 负责。

> Docker 镜像也已从 PDM 迁移到 uv,构建更快、层数缓存更友好。

## License

MIT
