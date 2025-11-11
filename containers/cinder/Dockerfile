# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/cinder:${OPENSTACK_VERSION}-ubuntu_jammy AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY python/cinder-understack /tmp/cinder-understack

RUN --mount=type=cache,target=/root/.cache/uv \
    cd /tmp/cinder-understack && \
    uv build --wheel --out-dir /tmp/wheels/

FROM quay.io/airshipit/cinder:${OPENSTACK_VERSION}-ubuntu_jammy AS final

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        patch \
        quilt \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=from=builder,source=/tmp/wheels,target=/tmp/wheels \
    /var/lib/openstack/bin/python -m pip install --no-input --find-links /tmp/wheels/ cinder-understack

COPY containers/cinder/patches /tmp/patches/
RUN cd /var/lib/openstack/lib/python3.10/site-packages && \
    QUILT_PATCHES=/tmp/patches quilt push -a
