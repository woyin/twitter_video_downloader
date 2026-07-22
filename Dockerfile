# 使用 Debian slim(比 alpine 兼容性好,无需 musl 编译工具)
FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    # 让容器直接用 uv 创建的 venv
    PATH="/app/.venv/bin:$PATH"

# 系统依赖:ffmpeg(yt-dlp 转码/合并用)、git、ca-certificates
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 从官方镜像拷入 uv(体积小、层缓存友好)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 先拷依赖描述 + lock,利用 Docker 层缓存(代码改动不会重装依赖)
COPY pyproject.toml uv.lock ./

# 只装运行依赖(frozen:严格按 lock;no-dev:不装开发依赖)
RUN uv sync --frozen --no-dev

# 拷源码
COPY main.py README.md ./

EXPOSE 8000

# shell 形式以便 ${PORT} 展开
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
