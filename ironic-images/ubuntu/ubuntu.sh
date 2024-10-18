#!/bin/bash

# ubuntu version
export DIB_RELEASE="${OS_VERSION:-noble}"

# devuser element - https://github.com/openstack/diskimage-builder/tree/master/diskimage_builder/elements/devuser
[[ -n $OS_VERSION ]] && sed -i -e "s|ubuntu-noble|ubuntu-${OS_VERSION}|" ubuntu.yaml
diskimage-builder ubuntu.yaml
