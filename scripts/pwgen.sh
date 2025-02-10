#!/bin/sh -e

export LC_ALL=C

# Default password length (32 characters)
LENGTH="${1:-32}"

# Default character set (alphanumeric + special characters)
CHARSET="${2:-_A-Z-a-z-0-9}"

dd bs=512 if=/dev/urandom count=1 2>/dev/null | tr -dc "$CHARSET" | head -c"$LENGTH"
echo
