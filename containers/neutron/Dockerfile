# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/neutron:${OPENSTACK_VERSION}-ubuntu_noble AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# renovate: name=openstack/neutron repo=https://github.com/rackerlabs/neutron.git branch=stable/2026.1
ARG NEUTRON_GIT_REF=1321ccbc5cd56d5502e2335c8a5a374801d88fb9
ADD --keep-git-dir=true https://github.com/rackerlabs/neutron.git#${NEUTRON_GIT_REF} /src/neutron
RUN git -C /src/neutron fetch --unshallow --tags

COPY python/neutron-understack /src/neutron-understack

ARG OPENSTACK_VERSION="required_argument"
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --upgrade \
      --constraint https://releases.openstack.org/constraints/upper/${OPENSTACK_VERSION} \
        /src/neutron \
        /src/neutron-understack

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/neutron:${OPENSTACK_VERSION}-ubuntu_noble AS final

COPY --from=build --link /var/lib/openstack /var/lib/openstack
