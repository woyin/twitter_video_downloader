# 使用 Python 3.12 Alpine 版本以获得最小镜像体积
FROM python:3.12-alpine

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# 默认端口
ENV PORT=8000

# 安装系统依赖 (ffmpeg 和 git 仍然是必需的)
# Alpine 使用 apk
RUN apk add --no-cache ffmpeg git

# 安装 PDM
RUN pip install --no-cache-dir pdm

# 复制依赖文件
COPY pyproject.toml pdm.lock ./

# 安装依赖
# 注意: 某些 Python 包在 Alpine 上可能需要编译工具 (gcc, musl-dev 等)
# 但 yt-dlp, fastapi, uvicorn 通常有 pure python wheel 或能在 alpine 上安装
RUN pdm install --prod --no-editable --no-self

# 复制源代码
COPY main.py ./
COPY README.md ./

# 暴露端口
EXPOSE $PORT

# 启动命令
CMD pdm run uvicorn main:app --host 0.0.0.0 --port $PORT
