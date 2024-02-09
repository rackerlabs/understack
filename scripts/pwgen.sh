#!/bin/sh -e

export LC_ALL=C
dd bs=512 if=/dev/urandom count=1 | tr -dc _A-Z-a-z-0-9 | head -c${1:-32}
echo
