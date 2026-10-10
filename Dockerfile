# GitHub-Trend-Learner 容器镜像（v1.8.3）
#
# 两阶段构建：
#   阶段 1（node）只负责把前端编译成静态资源，产物拷进阶段 2 后即丢弃，
#            最终镜像里不含 node_modules 与源码。
#   阶段 2（python）只装运行依赖，跑 Web 控制台。
#
# 构建：docker build -t github-trend-learner .
# 运行：docker run --rm -p 8000:8000 --env-file .env \
#          -v "$PWD/cache:/app/cache" -v "$PWD/outputs:/app/outputs" \
#          -v "$PWD/logs:/app/logs" github-trend-learner

# ---------- 阶段 1：构建前端 ----------
FROM node:20-alpine AS frontend-build

WORKDIR /build
# 先只拷依赖清单，让 npm ci 这层能被缓存（改业务代码不必重装依赖）
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ---------- 阶段 2：运行时 ----------
FROM python:3.12-slim

# 中文日志与文件名需要 UTF-8；PYTHONUNBUFFERED 让日志实时输出而非缓冲
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    UI_HOST=0.0.0.0 \
    UI_PORT=8000

WORKDIR /app

# 依赖单独一层，便于缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 后端与流水线代码
COPY app/ ./app/
COPY server/ ./server/
COPY main.py start_ui.py conftest.py ./

# 提示词与模板资产：运行时按相对路径读取，缺失会导致解析直接失败
COPY global.md ./
COPY agent/ ./agent/
COPY templates/ ./templates/

# 前端构建产物
COPY --from=frontend-build /build/dist ./frontend/dist

# 运行期会写入的目录（建议挂载卷，否则容器重建后丢失）
RUN mkdir -p cache logs outputs

# 以非 root 运行
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 健康检查：镜像内没有 curl，用 Python 标准库自检，避免额外依赖
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os,sys; \
url=f\"http://127.0.0.1:{os.getenv('UI_PORT','8000')}/api/health\"; \
sys.exit(0 if urllib.request.urlopen(url, timeout=4).status == 200 else 1)"

# --skip-build：前端已在阶段 1 构建完成，容器内没有 node，必须跳过
CMD ["python", "start_ui.py", "--skip-build", "--no-browser"]
