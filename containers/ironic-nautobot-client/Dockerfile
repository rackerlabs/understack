ARG BASE=ghcr.io/rackerlabs/understack/python3.11.8-alpine3.19:latest
FROM ${BASE} AS builder

RUN --mount=type=cache,target=/var/cache/apk apk add --virtual build-deps gcc python3-dev musl-dev linux-headers
RUN --mount=type=cache,target=/root/.cache/pip pip install 'wheel==0.43.0'
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# copy in the code
COPY --chown=appuser:appgroup python/understack-workflows /tmp/understack/python/understack-workflows
COPY --chown=appuser:appgroup python/understack-flavor-matcher /tmp/understack/python/understack-flavor-matcher

# install our requirements and our packages
RUN --mount=type=cache,target=/root/.cache/uv \
  uv venv /opt/venv --clear && \
  uv pip install \
    netifaces \
    psutil==6.1.1 \
    /tmp/understack/python/understack-workflows \
    /tmp/understack/python/understack-flavor-matcher

FROM ${BASE} AS prod
LABEL org.opencontainers.image.description="UnderStack Workflows"

COPY --from=builder --link /opt/venv /opt/venv

USER appuser
