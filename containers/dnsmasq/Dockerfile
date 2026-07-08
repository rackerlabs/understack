# syntax=docker/dockerfile:1
FROM debian:forky-slim AS prod

LABEL org.opencontainers.image.description="dnsmasq DNS-only for Understack"

RUN apt-get update && \
    apt-get -y install --no-install-recommends dnsmasq-base python3-jinja2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY containers/dnsmasq/common/helpers.sh /helpers.sh
COPY containers/dnsmasq/dnsmasq/entry-point.sh /entry-point.sh
RUN chmod +x /entry-point.sh
COPY containers/dnsmasq/dnsmasq/dnsmasq.conf.j2 /etc/dnsmasq.conf.j2
# let our entry point write out the script
RUN ln -sf /etc/dnsmasq.d/dnsmasq.conf /etc/dnsmasq.conf

ENTRYPOINT ["/entry-point.sh"]
CMD ["/usr/sbin/dnsmasq", "-d"]
