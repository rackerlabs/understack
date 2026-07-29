# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/nova:${OPENSTACK_VERSION}-ubuntu_noble AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# renovate: name=openstack/nova repo=https://github.com/rackerlabs/nova.git branch=understack/2026.1
ARG NOVA_GIT_REF=1602d7db7a3fe4930668f8a6534782adf4fbe572
ADD --keep-git-dir=true https://github.com/rackerlabs/nova.git#${NOVA_GIT_REF} /src/nova
RUN git -C /src/nova fetch --unshallow --tags

ARG OPENSTACK_VERSION="required_argument"
ADD https://releases.openstack.org/constraints/upper/${OPENSTACK_VERSION} /upper-constraints.txt

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --upgrade \
      --constraint /upper-constraints.txt \
        /src/nova

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/nova:${OPENSTACK_VERSION}-ubuntu_noble AS final

RUN rm -rf /var/lib/openstack
COPY --from=build --link /var/lib/openstack /var/lib/openstack

# Copy ironic_understack into Nova virt drivers
# This copies the directory as-is; no explicit dependencies are installed.
# Dependencies (requests, oslo_config) are already provided by Nova's installation.
COPY python/nova-understack/ironic_understack /var/lib/openstack/lib/python3.12/site-packages/nova/virt/ironic_understack
