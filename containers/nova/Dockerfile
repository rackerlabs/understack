# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/nova:${OPENSTACK_VERSION}-ubuntu_noble AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        patch \
        quilt \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY containers/nova/patches /tmp/patches/
RUN cd /var/lib/openstack/lib/python3.12/site-packages && \
    QUILT_PATCHES=/tmp/patches quilt push -a

COPY python/nova-understack/ironic_understack /var/lib/openstack/lib/python3.12/site-packages/nova/virt/ironic_understack

COPY python/keystoneauth-kubeservicetoken /src/keystoneauth-kubeservicetoken

ARG OPENSTACK_VERSION="required_argument"
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --constraint https://releases.openstack.org/constraints/upper/${OPENSTACK_VERSION} \
        /src/keystoneauth-kubeservicetoken

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/nova:${OPENSTACK_VERSION}-ubuntu_noble AS final

COPY --from=build --link /var/lib/openstack /var/lib/openstack
