FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.31 /uv /uvx /usr/local/bin/

ARG CERT_FILE

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENV SSL_CERT_FILE=/opt/etc/ssl/certs/snl-plus-zscaler.crt
ENV REQUESTS_CA_BUNDLE=/opt/etc/ssl/certs/snl-plus-zscaler.crt
ENV UV_NATIVE_TLS=true

WORKDIR /app

RUN if [ -z "$CERT_FILE" ]; then \
      echo "ERROR: CERT_FILE build argument is required."; \
      echo "Example:"; \
      echo "  podman build --build-arg CERT_FILE=certs/snl-plus-zscaler.crt -f Containerfile -t canary-distributed:dev ."; \
      exit 1; \
    fi

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/etc/ssl/certs

COPY ${CERT_FILE} /usr/local/share/ca-certificates/snl-plus-zscaler.crt

RUN update-ca-certificates \
    && cat /etc/ssl/certs/ca-certificates.crt /usr/local/share/ca-certificates/snl-plus-zscaler.crt > /opt/etc/ssl/certs/snl-plus-zscaler.crt \
    && chmod 0644 /opt/etc/ssl/certs/snl-plus-zscaler.crt

COPY pyproject.toml README.md ./
COPY src ./src

RUN uv --native-tls --no-cache pip install --system .

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/canary-distributed \
    && chown -R appuser:appuser /data

USER appuser

EXPOSE 8000

VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()" || exit 1

ENTRYPOINT ["canary-dist-server"]

CMD ["start", "--state-dir", "/data/canary-distributed", "--host", "0.0.0.0", "--port", "8000"]
