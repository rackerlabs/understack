#!/bin/sh

cd $(git rev-parse --show-toplevel)/openstack-helm && helm dep up "$1"
