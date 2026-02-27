# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/ironic:${OPENSTACK_VERSION}-ubuntu_noble AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        patch \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# clone source and patch it
# renovate: name=openstack/ironic repo=https://github.com/rackerlabs/ironic.git branch=understack/2025.2
ARG IRONIC_GIT_REF=c54301688290e9d086aa6c13acb96b561c45658e
ADD --keep-git-dir=true https://github.com/rackerlabs/ironic.git#${IRONIC_GIT_REF} /src/ironic
RUN git -C /src/ironic fetch --unshallow --tags

COPY python/ironic-understack /src/understack/ironic-understack
COPY python/understack-flavor-matcher /src/understack/understack-flavor-matcher

ARG OPENSTACK_VERSION="required_argument"
ARG NOVNC_VERSION=1.6.0
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --upgrade \
      --constraint https://releases.openstack.org/constraints/upper/${OPENSTACK_VERSION} \
        /src/ironic \
        /src/understack/ironic-understack \
        /src/understack/understack-flavor-matcher \
        proliantutils==2.16.3

COPY containers/ironic/patches /tmp/patches/
RUN cd /var/lib/openstack/lib/python3.12/site-packages && \
    patch -p1 < /tmp/patches/0001-Add-portgroup-name-validation-middleware-2025.2.patch
RUN cd /var/lib/openstack/lib/python3.12/site-packages && \
    patch -p1 < /tmp/patches/0002-Solve-IPMI-call-issue-results-in-UTF-8-format-error-.patch
RUN cd /var/lib/openstack/lib/python3.12/site-packages && \
    patch -p1 < /tmp/patches/0003-Handle-missing-storage-controller-mode-attribute.patch

# download and unpack novnc
RUN \
   export URL=https://github.com/novnc/noVNC/archive/refs/tags/v${NOVNC_VERSION}.tar.gz && \
   export DEST_FILE=novnc-${NOVNC_VERSION}.tar.gz && \
   export PFX=noVNC-${NOVNC_VERSION} && \
   rm -rf /usr/share/novnc/ && \
   mkdir -p /usr/share/novnc/ && \
   wget -q -O "$DEST_FILE" "$URL" && \
   tar -C /usr/share/novnc/ --strip-components=1 -zxvf "${DEST_FILE}" "$PFX/app" "$PFX/core" "$PFX/vendor" "$PFX/vnc.html"
COPY containers/ironic/ironic-console-pod.yaml.template /var/lib/openstack/lib/python3.12/site-packages/ironic/console/container/

FROM docker.io/debian:13 AS pxebuild
# example --build-arg IPXE_FLAGS="DEBUG=tcp:3,xfer:3,netdevice:2,ipv4:2,httpcore:2,httpconn:2"
ARG IPXE_FLAGS=""
RUN apt-get update && apt-get install -y git build-essential bison flex libssl-dev && mkdir /src
WORKDIR /src
RUN git clone https://github.com/ipxe/ipxe.git
COPY containers/ironic/ipxe-general.h /src/ipxe/src/config/local/general.h
COPY containers/ironic/ipxe-branding.h /src/ipxe/src/config/local/branding.h
WORKDIR /src/ipxe/src
RUN make bin-x86_64-efi/snponly.efi ${IPXE_FLAGS}

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
COPY --from=build /usr/share/novnc /usr/share/novnc
COPY --from=pxebuild  /src/ipxe/src/bin-x86_64-efi/snponly.efi /usr/lib/ipxe/snponly.efi
