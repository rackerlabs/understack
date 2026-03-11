FROM python:3.12-slim AS builder

RUN --mount=type=cache,target=/var/cache/apt \
  apt-get update && \
  apt-get install -y --no-install-recommends build-essential && \
  rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/pip pip install 'wheel==0.43.0'
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# copy in the code
COPY python/understack-workflows /tmp/understack/python/understack-workflows
COPY python/understack-flavor-matcher /tmp/understack/python/understack-flavor-matcher

# install our requirements and our packages
RUN --mount=type=cache,target=/root/.cache/uv \
  uv venv /opt/venv --clear && \
  uv pip install \
    --python /opt/venv/bin/python \
    netifaces \
    psutil==6.1.1 \
    /tmp/understack/python/understack-workflows \
    /tmp/understack/python/understack-flavor-matcher

FROM python:3.12-slim AS prod
LABEL org.opencontainers.image.description="UnderStack Workflows"
ENV PATH="/opt/venv/bin:${PATH}"

RUN groupadd --system --gid 10001 appgroup && \
  useradd --system --create-home --uid 10001 --gid appgroup appuser

COPY --from=builder --link /opt/venv /opt/venv

USER appuser
