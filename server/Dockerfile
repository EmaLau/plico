# Plico: strumenti PDF self-hosted sulla porta 8080.
# Contesto di build: la radice del repository (docker build -f server/Dockerfile .)

# 1. Documentazione: dai Markdown di docs/ alle pagine /docs (pandoc resta solo in questo stadio)
FROM debian:trixie-slim AS docs
ENV LANG=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends pandoc && rm -rf /var/lib/apt/lists/*
COPY docs/documentation.md docs/documentazione.md /src/docs/
COPY docs/web /src/docs/web
RUN sh /src/docs/web/build.sh /out

# 2. Servizio
FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY server/requirements.txt /tmp/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip ghostscript fonts-dejavu-core ca-certificates tini \
      tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng libgl1 libglib2.0-0 \
    && pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm -rf /var/lib/apt/lists/* /root/.cache /tmp/requirements.txt
ARG UID=1000
ARG GID=1000
RUN groupadd -g "$GID" plico 2>/dev/null || true \
    && useradd -u "$UID" -g "$GID" -M -d /work -s /usr/sbin/nologin plico 2>/dev/null || true \
    && mkdir -p /work && chown "$UID:$GID" /work
COPY server/server.py server/apikeys.py server/i18n.py server/ops.py server/chains.py server/converter.py server/magic.py /app/
COPY server/static /app/static
COPY --from=docs /out/ /app/static/
COPY server/selftest.py /app/selftest.py
ENV WORK_DIR=/work HOME=/work
USER ${UID}:${GID}
WORKDIR /app
EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
