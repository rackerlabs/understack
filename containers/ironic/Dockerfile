# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/ironic:${OPENSTACK_VERSION}-ubuntu_jammy AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY python/ironic-understack /tmp/understack/ironic-understack
COPY python/understack-flavor-matcher /tmp/understack/understack-flavor-matcher

RUN --mount=type=cache,target=/root/.cache/uv \
    for proj in $(find /tmp/understack -name pyproject.toml); do \
      cd $(dirname ${proj}) && uv build --wheel --out-dir /tmp/wheels/; \
    done

FROM quay.io/airshipit/ironic:${OPENSTACK_VERSION}-ubuntu_jammy AS final

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        genisoimage \
        isolinux \
        patch \
        quilt \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# pysnmp, pyasn1 and pyasn1-modules is only included to prevent proliantutils
# from upgrading to too newer of a version. when we have the constraints file we need to delete that
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=from=builder,source=/tmp/wheels,target=/tmp/wheels \
    /var/lib/openstack/bin/python -m pip install --no-input --find-links /tmp/wheels/ \
      ironic-understack \
      understack-flavor-matcher \
      sushy-oem-idrac==6.0.0 \
      proliantutils==2.16.3 \
      pysnmp==5.1.0 \
      pyasn1==0.5.1 \
      'pyasn1-modules<0.4.0'
#COPY containers/ironic/patches /tmp/patches/
#RUN cd /var/lib/openstack/lib/python3.10/site-packages && \
#    QUILT_PATCHES=/tmp/patches quilt push -a
