# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/keystone:${OPENSTACK_VERSION}-ubuntu_jammy

# renovate: datasource=github-releases depName=OpenIDC/mod_auth_openidc
ARG MOD_AUTH_OPENIDC_VERSION=2.4.16.5
ARG MOD_AUTH_OPENIDC_SHA256=deb52ea8304a41ee0331e4ba87a9f82ff643464b6d34084e161f58ec11c25a69
ADD --checksum=sha256:${MOD_AUTH_OPENIDC_SHA256} https://github.com/OpenIDC/mod_auth_openidc/releases/download/v${MOD_AUTH_OPENIDC_VERSION}/libapache2-mod-auth-openidc_${MOD_AUTH_OPENIDC_VERSION}-1.jammy_amd64.deb /tmp

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        /tmp/libapache2-mod-auth-openidc_${MOD_AUTH_OPENIDC_VERSION}-1.jammy_amd64.deb \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/*.deb
