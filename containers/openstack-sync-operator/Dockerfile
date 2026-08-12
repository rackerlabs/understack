# syntax=docker/dockerfile:1

FROM ghcr.io/flant/shell-operator:v1.13.1 AS prod
LABEL org.opencontainers.image.description="OpenStack sync shell-operator"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN --mount=type=cache,target=/var/cache/apk apk add python3
RUN python3 -m venv /opt/venv
ENV VIRTUAL_ENV="/opt/venv"
ENV PATH="/opt/venv/bin:$PATH"

COPY python/openstack-sync /src/openstack-sync
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --upgrade \
        /src/openstack-sync

COPY --chmod=755 python/openstack-sync/openstack_sync/hooks/placeholder.py /hooks/placeholder.py
COPY --chmod=755 python/openstack-sync/openstack_sync/hooks/router_flavors.py /hooks/router_flavors.py
