# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/skyline:${OPENSTACK_VERSION}-ubuntu_noble AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY python/keystoneauth-kubeservicetoken /src/keystoneauth-kubeservicetoken

ARG OPENSTACK_VERSION="required_argument"
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --constraint https://releases.openstack.org/constraints/upper/${OPENSTACK_VERSION} \
        /src/keystoneauth-kubeservicetoken

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/skyline:${OPENSTACK_VERSION}-ubuntu_noble AS final

COPY --from=build --link /var/lib/openstack /var/lib/openstack
