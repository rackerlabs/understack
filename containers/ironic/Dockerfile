# syntax=docker/dockerfile:1

ARG OPENSTACK_VERSION="required_argument"
FROM quay.io/airshipit/venv_builder:${OPENSTACK_VERSION}-ubuntu_noble AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        patch \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# renovate: name=openstack/ironic repo=https://github.com/rackerlabs/ironic.git branch=understack/2026.1
ARG IRONIC_GIT_REF=6700c020ecf29253fff19dddda85935099ab773e
ADD --keep-git-dir=true https://github.com/rackerlabs/ironic.git#${IRONIC_GIT_REF} /src/ironic
RUN git -C /src/ironic fetch --unshallow --tags

# renovate: name=openstack/sushy repo=https://github.com/openstack/sushy.git branch=stable/2026.1
ARG SUSHY_GIT_REF=b97264ef5b7a51a577889bf60c139e0db0b2fe9a
ADD --keep-git-dir=true https://github.com/openstack/sushy.git#${SUSHY_GIT_REF} /src/sushy
RUN git -C /src/sushy fetch --unshallow --tags && \
    sed -i '/sushy==.*/d' /upper-constraints.txt

COPY python/ironic-understack /src/understack/ironic-understack

# Override the oslo.messaging pin from the 2026.1 upper-constraints (17.3.1) to pull in
# the QManager reply-queue collision fix (bug/2110957), backported to stable/2026.1 and
# released as 17.3.2. This stays within the 2026.1 (17.x) release line.
ARG OSLO_MESSAGING_VERSION=17.3.2
RUN sed -i '/^oslo.messaging===.*/d' /upper-constraints.txt

ARG OPENSTACK_VERSION="required_argument"
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      --upgrade \
      --constraint /upper-constraints.txt \
        /src/ironic \
        /src/sushy \
        /src/understack/ironic-understack \
        proliantutils==2.16.3 \
        "oslo.messaging==${OSLO_MESSAGING_VERSION}"

COPY containers/ironic/patches /tmp/patches/
RUN cd /var/lib/openstack/lib/python3.12/site-packages && \
    patch -p1 < /tmp/patches/0002-Solve-IPMI-call-issue-results-in-UTF-8-format-error-.patch

# download and unpack novnc
ARG NOVNC_VERSION=1.6.0
RUN \
   export URL=https://github.com/novnc/noVNC/archive/refs/tags/v${NOVNC_VERSION}.tar.gz && \
   export DEST_FILE=novnc-${NOVNC_VERSION}.tar.gz && \
   export PFX=noVNC-${NOVNC_VERSION} && \
   rm -rf /usr/share/novnc/ && \
   mkdir -p /usr/share/novnc/ && \
   wget -q -O "$DEST_FILE" "$URL" && \
   tar -C /usr/share/novnc/ --strip-components=1 -zxvf "${DEST_FILE}" "$PFX/app" "$PFX/core" "$PFX/vendor" "$PFX/vnc.html"
COPY containers/ironic/ironic-console-pod.yaml.template /var/lib/openstack/lib/python3.12/site-packages/ironic/console/container/

# renovate: datasource=docker depName=ghcr.io/rackerlabs/understack/ironic-ipxe versioning=semver
FROM ghcr.io/rackerlabs/understack/ironic-ipxe:1.0.0 AS ipxe

FROM quay.io/airshipit/ironic:${OPENSTACK_VERSION}-ubuntu_noble AS final

ENV PATH="/var/lib/openstack/bin:$PATH"

RUN <<EOF bash -xe
wget -qO- https://pkgs.k8s.io/core:/stable:/v1.35/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
chmod 644 /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.35/deb/ /' > /etc/apt/sources.list.d/kubernetes.list
chmod 644 /etc/apt/sources.list.d/kubernetes.list
EOF

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        genisoimage \
        isolinux \
        kubectl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=build --link /var/lib/openstack /var/lib/openstack
COPY --from=build /usr/share/novnc /usr/share/novnc
COPY --from=ipxe /snponly.efi /usr/lib/ipxe/snponly.efi
