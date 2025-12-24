# Twitter/X Video Downloader API

这是一个简单、轻量级的 API 服务，用于解析 Twitter (X) 帖子中的视频真实下载地址。它基于强大的 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 库构建，并封装为 Docker 镜像，方便快速部署。

## 特性

*   🚀 **开箱即用**: 提供 Docker 镜像，一键部署。
*   🎥 **智能解析**: 自动过滤 M3U8 流，直接提取最高画质的 MP4 直链。
*   🔒 **安全鉴权**: 支持可选的 API Key 鉴权机制。
*   ⚡ **高性能**: 基于 FastAPI 和 Uvicorn 构建，响应迅速。

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
      # 可选：设置 API 鉴权密钥。如果不设置，API 将公开访问。
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
*   `xid`: Twitter/X 帖子 URL (例如 `https://x.com/user/status/123456`)
*   `x-api-key`: (如果在环境变量中设置了 API_KEY) 鉴权密钥

**示例**:
```bash
curl "http://localhost:8000/extract?xid=https://x.com/SpaceX/status/1871329241904255193&x-api-key=your_secret_key"
```

### 提取视频 (POST)

**端点**: `/extract`

**Header**:
*   `x-api-key`: (如果在环境变量中设置了 API_KEY) 鉴权密钥

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

## 开发

本项目使用 [PDM](https://pdm.fming.dev/) 进行依赖管理。

1.  克隆仓库
2.  安装依赖: `pdm install`
3.  运行测试: `pdm run uvicorn main:app --reload`

## License

MIT
