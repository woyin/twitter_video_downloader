# Debian slim:glibc 兼容性优于 alpine,无需 musl 编译工具链
FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    WEB_CONCURRENCY=1 \
    PATH="/app/.venv/bin:$PATH"

# ca-certificates 供 yt-dlp 访问 HTTPS;本服务不下载媒体,不需要 ffmpeg。
# git 只在构建镜像时用不到,已移除。
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 从官方镜像拷入 uv(体积小、层缓存友好)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 先拷依赖描述 + lock,利用 Docker 层缓存(代码改动不会重装依赖)
COPY pyproject.toml uv.lock ./

# 只装运行依赖(frozen:严格按 lock;no-dev:不装开发依赖)
RUN uv sync --frozen --no-dev

# 拷源码
COPY main.py README.md ./

# 以非 root 用户运行
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/', timeout=3)"

# shell 形式以便 ${PORT} 与 ${WEB_CONCURRENCY} 展开
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY}
