# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/keystone:${OPENSTACK_VERSION}-ubuntu_noble AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# renovate: name=openstack/keystone repo=https://github.com/rackerlabs/keystone.git branch=understack/2026.1
ARG KEYSTONE_GIT_REF=f01950b7caf547970e961c076b74f6157b7bad84
ADD --keep-git-dir=true https://github.com/rackerlabs/keystone.git#${KEYSTONE_GIT_REF} /src/keystone
RUN git -C /src/keystone fetch --unshallow --tags

ARG OPENSTACK_VERSION="required_argument"
ADD https://releases.openstack.org/constraints/upper/${OPENSTACK_VERSION} /upper-constraints.txt

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --upgrade \
      --constraint /upper-constraints.txt \
        /src/keystone

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/keystone:${OPENSTACK_VERSION}-ubuntu_noble AS final

# renovate: datasource=github-releases depName=OpenIDC/mod_auth_openidc
ARG MOD_AUTH_OPENIDC_VERSION=2.4.16.11
ARG MOD_AUTH_OPENIDC_SHA256=431c4ffb0e26d59ef0e60afa0fdeab61466faeecafdd237355fdcccf7858b37f
ADD --checksum=sha256:${MOD_AUTH_OPENIDC_SHA256} https://github.com/OpenIDC/mod_auth_openidc/releases/download/v${MOD_AUTH_OPENIDC_VERSION}/libapache2-mod-auth-openidc_${MOD_AUTH_OPENIDC_VERSION}-1.noble_amd64.deb /tmp

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        /tmp/libapache2-mod-auth-openidc_${MOD_AUTH_OPENIDC_VERSION}-1.noble_amd64.deb \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/*.deb

RUN rm -rf /var/lib/openstack
COPY --from=build --link /var/lib/openstack /var/lib/openstack
