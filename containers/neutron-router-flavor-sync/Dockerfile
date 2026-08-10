# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM ghcr.io/flant/shell-operator:v1.13.1 AS prod
LABEL org.opencontainers.image.description="Neutron router flavor sync shell-operator"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN --mount=type=cache,target=/var/cache/apk apk add python3
RUN python3 -m venv /opt/venv
ENV VIRTUAL_ENV="/opt/venv"
ENV PATH="/opt/venv/bin:$PATH"

ARG OPENSTACK_VERSION="required_argument"
ADD https://releases.openstack.org/constraints/upper/${OPENSTACK_VERSION} /upper-constraints.txt
COPY python/understack-neutron-flavors /src/understack-neutron-flavors
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --upgrade \
      --constraint /upper-constraints.txt \
        /src/understack-neutron-flavors

COPY --chmod=755 python/understack-neutron-flavors/understack_neutron_flavors/router_flavors.py /hooks/router_flavors.py
