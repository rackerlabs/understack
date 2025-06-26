# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM docker.io/openstackhelm/cinder:${OPENSTACK_VERSION}-ubuntu_jammy AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY python/cinder-understack /tmp/cinder-understack

RUN --mount=type=cache,target=/root/.cache/uv \
    cd /tmp/cinder-understack && \
    uv build --wheel --out-dir /tmp/wheels/

FROM docker.io/openstackhelm/cinder:${OPENSTACK_VERSION}-ubuntu_jammy AS final

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=from=builder,source=/tmp/wheels,target=/tmp/wheels \
    /var/lib/openstack/bin/python -m pip install --no-input --find-links /tmp/wheels/ cinder-understack
