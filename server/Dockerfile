# Universal-PDF: strumenti PDF self-hosted sulla porta 8080.
FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-fastapi python3-uvicorn python3-pil ghostscript \
      fonts-dejavu-core ca-certificates tini \
    && pip3 install --no-cache-dir --break-system-packages pymupdf==1.26.5 pikepdf==9.11.0 python-multipart==0.0.20 \
    && rm -rf /var/lib/apt/lists/* /root/.cache
ARG UID=1000
ARG GID=1000
RUN groupadd -g "$GID" upd 2>/dev/null || true \
    && useradd -u "$UID" -g "$GID" -M -d /work -s /usr/sbin/nologin upd 2>/dev/null || true \
    && mkdir -p /work && chown "$UID:$GID" /work
COPY server.py apikeys.py /app/
COPY static /app/static
COPY selftest.py /app/selftest.py
ENV WORK_DIR=/work HOME=/work
USER ${UID}:${GID}
WORKDIR /app
EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
