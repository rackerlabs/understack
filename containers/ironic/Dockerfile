# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/ironic:${OPENSTACK_VERSION}-ubuntu_noble AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY python/ironic-understack /src/understack/ironic-understack
COPY python/understack-flavor-matcher /src/understack/understack-flavor-matcher

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        patch \
        quilt \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ARG OPENSTACK_VERSION="required_argument"
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --constraint https://releases.openstack.org/constraints/upper/${OPENSTACK_VERSION} \
        /src/understack/ironic-understack \
        /src/understack/understack-flavor-matcher \
        proliantutils==2.16.3

COPY containers/ironic/patches /tmp/patches/
RUN cd /var/lib/openstack/lib/python3.12/site-packages && \
    QUILT_PATCHES=/tmp/patches quilt push -a

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/ironic:${OPENSTACK_VERSION}-ubuntu_noble AS final

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN wget -qO- https://pkgs.k8s.io/core:/stable:/v1.35/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg && \
    chmod 644 /etc/apt/keyrings/kubernetes-apt-keyring.gpg && \
    echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.35/deb/ /' > /etc/apt/sources.list.d/kubernetes.list && \
    chmod 644 /etc/apt/sources.list.d/kubernetes.list

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        genisoimage \
        isolinux \
        kubectl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=build --link /var/lib/openstack /var/lib/openstack
