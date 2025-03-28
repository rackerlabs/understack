# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM docker.io/openstackhelm/ironic:${OPENSTACK_VERSION}-ubuntu_jammy AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY python/ironic-understack /tmp/understack/ironic-understack
COPY python/understack-flavor-matcher /tmp/understack/understack-flavor-matcher

RUN --mount=type=cache,target=/root/.cache/uv \
    for proj in $(find /tmp/understack -name pyproject.toml); do \
      cd $(dirname ${proj}) && uv build --wheel --out-dir /tmp/wheels/; \
    done

FROM docker.io/openstackhelm/ironic:${OPENSTACK_VERSION}-ubuntu_jammy AS final

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        genisoimage \
        isolinux \
        patch \
        quilt \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=from=builder,source=/tmp/wheels,target=/tmp/wheels \
    /var/lib/openstack/bin/python -m pip install --no-input --find-links /tmp/wheels/ \
      ironic-understack \
      understack-flavor-matcher \
      sushy-oem-idrac==6.0.0
COPY containers/ironic/patches /tmp/patches/
RUN cd /var/lib/openstack/lib/python3.10/site-packages && \
    QUILT_PATCHES=/tmp/patches quilt push -a
