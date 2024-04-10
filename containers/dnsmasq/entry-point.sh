#!/bin/sh

set -eux

. /helpers.sh

mkdir -p /etc/dnsmasq.d/
mkdir -p /etc/dnsmasq.d/hostsdir.d
mkdir -p /etc/dnsmasq.d/optsdir.d

render_j2_file /etc/dnsmasq.conf.j2 /etc/dnsmasq.conf

/usr/sbin/dnsmasq --test

case "$1" in
    *sh|*dnsmasq) exec "$@" ;;
    *) exec /usr/sbin/dnsmasq "$@" ;;
esac
