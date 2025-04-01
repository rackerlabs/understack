# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/octavia:${OPENSTACK_VERSION}-ubuntu_jammy

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        patch \
        quilt \
        libunbound-dev \
        libunwind-dev \
        python3-unbound \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install -U ovn-octavia-provider ovsdbapp
