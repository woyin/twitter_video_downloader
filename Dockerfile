# 使用 Python 3.12 slim 版本作为基础镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
# 防止 Python 写入 pyc 文件
ENV PYTHONDONTWRITEBYTECODE=1
# 防止 Python 缓冲 stdout 和 stderr
ENV PYTHONUNBUFFERED=1
# 设置 ffmpeg 位置 (yt-dlp有时需要)
ENV DEBIAN_FRONTEND=noninteractive

# 安装系统依赖 (包括 ffmpeg 和 git，git 有时用于安装 git 依赖)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 安装 PDM
RUN pip install --no-cache-dir pdm

# 复制依赖文件
COPY pyproject.toml pdm.lock ./

# 安装依赖
# --prod: 不安装开发依赖
# --no-editable: 不安装为可编辑模式
# --no-self: 不安装当前项目包本身（只安装依赖）
RUN pdm install --prod --no-editable --no-self

# 复制源代码
COPY main.py ./
# COPY README.md ./

# 如果项目作为一个包安装，可以去掉 --no-self 并在这里运行 pdm install
# 目前看来是个单文件脚本，直接复制即可

# 默认端口
ENV PORT=8000

# 暴露端口
EXPOSE $PORT

# 启动命令
# 使用 pdm run 或者直接调用 uvicorn (如果安装在 .venv 中)
# 使用 pdm run 比较方便，它会自动处理 venv
CMD pdm run uvicorn main:app --host 0.0.0.0 --port $PORT
