# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/neutron:${OPENSTACK_VERSION}-ubuntu_noble AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# renovate: name=openstack/neutron repo=https://github.com/rackerlabs/neutron.git branch=understack/2026.1
ARG NEUTRON_GIT_REF=f02658b3721de198f2dac04e7eb64ef9eb320732
ADD --keep-git-dir=true https://github.com/rackerlabs/neutron.git#${NEUTRON_GIT_REF} /src/neutron
RUN git -C /src/neutron fetch --unshallow --tags

# renovate: name=openstack/neutron-lib repo=https://github.com/rackerlabs/neutron-lib.git branch=understack/2026.1
ARG NEUTRON_LIB_GIT_REF=6d0367183cc92656ba449acefd830cb4e11f2f5b
ADD --keep-git-dir=true https://github.com/rackerlabs/neutron-lib.git#${NEUTRON_LIB_GIT_REF} /src/neutron-lib
RUN git -C /src/neutron-lib fetch --unshallow --tags

COPY python/neutron-understack /src/neutron-understack

ARG OPENSTACK_VERSION="required_argument"
ADD https://releases.openstack.org/constraints/upper/${OPENSTACK_VERSION} /upper-constraints.txt
RUN sed -i '/^neutron-lib==.*/d' /upper-constraints.txt

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --upgrade \
      --constraint /upper-constraints.txt \
        /src/neutron \
        /src/neutron-lib \
        /src/neutron-understack

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/neutron:${OPENSTACK_VERSION}-ubuntu_noble AS final

RUN rm -rf /var/lib/openstack
COPY --from=build --link /var/lib/openstack /var/lib/openstack
