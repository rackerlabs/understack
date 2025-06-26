# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM docker.io/openstackhelm/keystone:${OPENSTACK_VERSION}-ubuntu_jammy

ADD --checksum=sha256:deb52ea8304a41ee0331e4ba87a9f82ff643464b6d34084e161f58ec11c25a69 https://github.com/OpenIDC/mod_auth_openidc/releases/download/v2.4.16.5/libapache2-mod-auth-openidc_2.4.16.5-1.jammy_amd64.deb /tmp

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        /tmp/libapache2-mod-auth-openidc_2.4.16.5-1.jammy_amd64.deb \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/*.deb
