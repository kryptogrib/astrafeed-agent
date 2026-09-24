FROM python:3.12-slim

ARG GIT_COMMIT=unknown
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GIT_COMMIT=$GIT_COMMIT

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
COPY src ./src
# Install uv from PyPI so the image build does not hang on ghcr.io metadata.
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --compile-bytecode \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown app:app /data

USER app
VOLUME ["/data"]
CMD ["/app/.venv/bin/astrafeed-serve"]
