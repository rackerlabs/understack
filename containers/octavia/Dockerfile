# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/octavia:${OPENSTACK_VERSION}-ubuntu_jammy AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ARG OPENSTACK_VERSION="required_argument"
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --constraint https://releases.openstack.org/constraints/upper/${OPENSTACK_VERSION} \
        ovn-octavia-provider \
        ovsdbapp

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/octavia:${OPENSTACK_VERSION}-ubuntu_jammy AS final

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libunbound-dev \
        libunwind-dev \
        python3-unbound \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=build --link /var/lib/openstack /var/lib/openstack
