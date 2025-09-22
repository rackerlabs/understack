# NOTE: This container is used only for local development and is not
# intended to be used in CI/production
FROM ubuntu:24.04

RUN apt-get update && \
  apt-get -y  --no-install-recommends install debootstrap qemu-utils squashfs-tools kpartx python3-pip python3-virtualenv sudo psutils procps git-core cpio
