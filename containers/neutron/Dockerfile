# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/neutron:${OPENSTACK_VERSION}-ubuntu_noble AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# renovate: name=openstack/neutron repo=https://github.com/rackerlabs/neutron.git branch=stable/2025.2
ARG NEUTRON_GIT_REF=feca3f33e610555099caececa990f18c2bad8c9c
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
