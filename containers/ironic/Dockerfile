# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/ironic:${OPENSTACK_VERSION}-ubuntu_jammy AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY python/ironic-understack /src/understack/ironic-understack
COPY python/understack-flavor-matcher /src/understack/understack-flavor-matcher

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        patch \
        quilt \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ARG OPENSTACK_VERSION="required_argument"
# pysnmp, pyasn1 and pyasn1-modules is only included to prevent proliantutils
# from upgrading to too newer of a version.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --constraint https://releases.openstack.org/constraints/upper/${OPENSTACK_VERSION} \
        /src/ironic-understack \
        /src/understack-flavor-matcher \
        sushy-oem-idrac==6.0.0 \
        proliantutils==2.16.3 \
        pysnmp==5.1.0 \
        pyasn1==0.5.1 \
        'pyasn1-modules<0.4.0'

COPY containers/ironic/patches /tmp/patches/
RUN cd /var/lib/openstack/lib/python3.10/site-packages && \
    QUILT_PATCHES=/tmp/patches quilt push -a

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/ironic:${OPENSTACK_VERSION}-ubuntu_jammy AS final

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        genisoimage \
        isolinux \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=build --link /var/lib/openstack /var/lib/openstack
