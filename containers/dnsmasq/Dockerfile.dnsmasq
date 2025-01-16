# syntax=docker/dockerfile:1
FROM debian:bookworm-20240408-slim AS builder

ENV DEBFULLNAME="Marek Skrobacki"
ENV DEBEMAIL="marek.skrobacki@rackspace.co.uk"
ENV QUILT_PATCHES=debian/patches

RUN echo "deb-src http://deb.debian.org/debian bookworm main" > /etc/apt/sources.list
RUN apt-get update && apt-get -y install \
    build-essential \
    devscripts \
    fakeroot \
    debhelper \
    automake \
    autotools-dev \
    pkg-config \
    ca-certificates \
    quilt \
    --no-install-recommends
WORKDIR /src
RUN apt-get -y build-dep dnsmasq
RUN apt-get -y source dnsmasq
# copy in our patch
COPY dnsmasq/dhcp-allowed-srvids.patch /src/
# setup the patch to be built into the quilt file
# set our version number to a local override suffixed by '.uc1'
RUN cd /src/dnsmasq-* && \
    mkdir -p debian/patches && \
    mv /src/dhcp-allowed-srvids.patch debian/patches && \
    dch -l .uc "patched for dhcp-allowed-srvids" && \
    echo dhcp-allowed-srvids.patch >> debian/patches/series && \
    quilt push -a
# build it
RUN cd /src/dnsmasq-* && dpkg-buildpackage -rfakeroot


FROM debian:bookworm-20240408-slim AS prod

LABEL org.opencontainers.image.description="dnsmasq for Understack's Ironic"

COPY --from=builder /src/dnsmasq-base_*_amd64.deb /tmp
COPY --from=builder /src/dnsmasq_*_all.deb /tmp

RUN apt-get update && \
    apt-get -y install --no-install-recommends python3-jinja2 && \
    apt-get -y --fix-broken install --no-install-recommends /tmp/dnsmasq-base_*_amd64.deb /tmp/dnsmasq_*_all.deb && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/*.deb

COPY common/helpers.sh /helpers.sh
COPY dnsmasq/entry-point.sh /entry-point.sh
RUN chmod +x /entry-point.sh
COPY dnsmasq/dnsmasq.conf.j2 /etc/dnsmasq.conf.j2
# let our entry point write out the script
RUN ln -sf /etc/dnsmasq.d/dnsmasq.conf /etc/dnsmasq.conf

ENTRYPOINT ["/entry-point.sh"]
CMD ["/usr/sbin/dnsmasq", "-d"]
