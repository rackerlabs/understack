#!/bin/sh

LC_ALL=C tr -dc _A-Z-a-z-0-9 < /dev/urandom | head -c${1:-32}
echo
