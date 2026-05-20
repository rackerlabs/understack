# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/keystone:${OPENSTACK_VERSION}-ubuntu_noble

# renovate: datasource=github-releases depName=OpenIDC/mod_auth_openidc
ARG MOD_AUTH_OPENIDC_VERSION=2.4.16.11
ARG MOD_AUTH_OPENIDC_SHA256=431c4ffb0e26d59ef0e60afa0fdeab61466faeecafdd237355fdcccf7858b37f
ADD --checksum=sha256:${MOD_AUTH_OPENIDC_SHA256} https://github.com/OpenIDC/mod_auth_openidc/releases/download/v${MOD_AUTH_OPENIDC_VERSION}/libapache2-mod-auth-openidc_${MOD_AUTH_OPENIDC_VERSION}-1.noble_amd64.deb /tmp

# renovate: datasource=github-releases depName=OpenIDC/liboauth2
ARG LIBOAUTH2_VERSION=2.2.1
ARG LIBOAUTH2_SHA256=a971d00469b27679c49d4f0e792261512125598a063aea4593a0fe174188acea
ARG LIBOAUTH2_APACHE_SHA256=a6dcb37bbbde47862aa298df71b63ca5237ceb9ebf88faa1598157994fc30855
ADD --checksum=sha256:${LIBOAUTH2_SHA256} https://github.com/OpenIDC/liboauth2/releases/download/v${LIBOAUTH2_VERSION}/liboauth2_${LIBOAUTH2_VERSION}-1.noble_amd64.deb /tmp
ADD --checksum=sha256:${LIBOAUTH2_APACHE_SHA256} https://github.com/OpenIDC/liboauth2/releases/download/v${LIBOAUTH2_VERSION}/liboauth2-apache_${LIBOAUTH2_VERSION}-1.noble_amd64.deb /tmp

# renovate: datasource=github-releases depName=OpenIDC/mod_oauth2
ARG MOD_OAUTH2_VERSION=4.1.0
ARG MOD_OAUTH2_SHA256=717bf50c7b7c6e25375d350ec5c0fef4e1971a97ffc5efc5732f52d38bceb07a
ADD --checksum=sha256:${MOD_OAUTH2_SHA256} https://github.com/OpenIDC/mod_oauth2/releases/download/v${MOD_OAUTH2_VERSION}/libapache2-mod-oauth2_${MOD_OAUTH2_VERSION}-1.noble_amd64.deb /tmp

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        /tmp/libapache2-mod-auth-openidc_${MOD_AUTH_OPENIDC_VERSION}-1.noble_amd64.deb \
        /tmp/liboauth2_${LIBOAUTH2_VERSION}-1.noble_amd64.deb \
        /tmp/liboauth2-apache_${LIBOAUTH2_VERSION}-1.noble_amd64.deb \
        /tmp/libapache2-mod-oauth2_${MOD_OAUTH2_VERSION}-1.noble_amd64.deb \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/*.deb
