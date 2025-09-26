#!/bin/sh

set -eux

# shellcheck disable=SC1091
# This is irrelevant because this only runs inside of a container.
. /helpers.sh

mkdir -p /etc/dnsmasq.d/
mkdir -p /etc/dnsmasq.d/hostsdir.d
mkdir -p /etc/dnsmasq.d/optsdir.d

render_j2_file /etc/dnsmasq.conf.j2 /etc/dnsmasq.conf

if [ -n "${DEBUG_DNSMASQ_CONF+x}" ]; then
  cat /etc/dnsmasq.conf >&2
fi

/usr/sbin/dnsmasq --test

case "$1" in
    *sh|*dnsmasq) exec "$@" ;;
    *) exec /usr/sbin/dnsmasq "$@" ;;
esac
