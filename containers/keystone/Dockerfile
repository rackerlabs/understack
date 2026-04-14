# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/keystone:${OPENSTACK_VERSION}-ubuntu_noble

# renovate: datasource=github-releases depName=OpenIDC/mod_auth_openidc
ARG MOD_AUTH_OPENIDC_VERSION=v2.4.19
ARG MOD_AUTH_OPENIDC_SHA256=431c4ffb0e26d59ef0e60afa0fdeab61466faeecafdd237355fdcccf7858b37f
ADD --checksum=sha256:${MOD_AUTH_OPENIDC_SHA256} https://github.com/OpenIDC/mod_auth_openidc/releases/download/v${MOD_AUTH_OPENIDC_VERSION}/libapache2-mod-auth-openidc_${MOD_AUTH_OPENIDC_VERSION}-1.noble_amd64.deb /tmp

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        /tmp/libapache2-mod-auth-openidc_${MOD_AUTH_OPENIDC_VERSION}-1.noble_amd64.deb \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/*.deb
