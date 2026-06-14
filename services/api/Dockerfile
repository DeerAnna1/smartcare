FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install \
    -i https://pypi.tuna.tsinghua.edu.cn/simple/ \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    --timeout 300 --retries 5 \
    -r requirements.txt


# ─── Runtime ────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# 仅运行期需要 libpq5（asyncpg 不需要，但保留以兼容同步驱动 / 工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 1001 --gid 0 --create-home apiuser

COPY --from=builder /install /usr/local

# Pre-create model cache directories with correct ownership
RUN mkdir -p /home/apiuser/.cache/huggingface \
    /home/apiuser/.cache/chroma \
    && chown -R apiuser:0 /home/apiuser/.cache

COPY --chown=apiuser:0 . .

USER apiuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO \
    LOG_FORMAT=json \
    WORKERS=2

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# 生产用 gunicorn + uvicorn worker；开发用 docker-compose 覆盖 command 启 --reload
CMD ["sh", "-c", "gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w ${WORKERS} -b 0.0.0.0:8000 --timeout 90 --graceful-timeout 30 --access-logfile - --error-logfile -"]
