FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    WEB_CONCURRENCY=1 \
    FORWARDED_ALLOW_IPS=127.0.0.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN addgroup --system omr && adduser --system --ingroup omr --home /app omr
COPY --chown=omr:omr . ./
RUN mkdir -p /app/uploads && chown -R omr:omr /app/uploads

USER omr
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4)" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
