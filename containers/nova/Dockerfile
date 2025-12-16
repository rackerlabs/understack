# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/nova:${OPENSTACK_VERSION}-ubuntu_noble

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        patch \
        quilt \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY containers/nova/patches /tmp/patches/
RUN cd /var/lib/openstack/lib/python3.12/site-packages && \
    QUILT_PATCHES=/tmp/patches quilt push -a
COPY python/nova-understack/ironic_understack  /var/lib/openstack/lib/python3.12/site-packages/nova/virt/ironic_understack
