# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/neutron:${OPENSTACK_VERSION}-ubuntu_jammy AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY python/neutron-understack /tmp/neutron-understack

RUN --mount=type=cache,target=/root/.cache/uv \
    cd /tmp/neutron-understack && \
    uv build --wheel --out-dir /tmp/wheels/

FROM quay.io/airshipit/neutron:${OPENSTACK_VERSION}-ubuntu_jammy AS final

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=from=builder,source=/tmp/wheels,target=/tmp/wheels \
    /var/lib/openstack/bin/python -m pip install --no-input --find-links /tmp/wheels/ neutron-understack
